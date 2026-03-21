package com.pilot.app.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.graphics.Rect
import android.os.Bundle
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.pilot.app.model.ScreenState
import com.pilot.app.model.UIElement
import com.pilot.app.util.Constants
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

class PilotAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "PilotA11y"
        var instance: PilotAccessibilityService? = null
            private set
    }

    private var nodeMap: MutableMap<Int, AccessibilityNodeInfo> = mutableMapOf()

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.i(TAG, "Accessibility service connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // We don't react to individual events; we poll the screen on demand.
    }

    override fun onInterrupt() {
        Log.w(TAG, "Accessibility service interrupted")
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    // ── Screen Reading ──────────────────────────────────────────────

    fun readScreen(): ScreenState {
        nodeMap.clear()
        val root = rootInActiveWindow ?: return emptyScreenState()
        val elements = mutableListOf<UIElement>()
        var idCounter = 1

        traverseNode(root, elements) { idCounter++ ; idCounter - 1 }

        val packageName = root.packageName?.toString() ?: "unknown"

        val title = findScreenTitle(root)

        root.recycle()

        val capped = capElements(elements)

        return ScreenState(
            packageName = packageName,
            activity = null,
            screenTitle = title,
            timestamp = System.currentTimeMillis() / 1000,
            elements = capped
        )
    }

    private fun traverseNode(
        node: AccessibilityNodeInfo,
        elements: MutableList<UIElement>,
        nextId: () -> Int
    ) {
        val bounds = Rect()
        node.getBoundsInScreen(bounds)

        if (bounds.width() <= 0 || bounds.height() <= 0) {
            return
        }

        val text = node.text?.toString()
        val contentDesc = node.contentDescription?.toString()
        val resourceId = node.viewIdResourceName
        val isClickable = node.isClickable
        val isScrollable = node.isScrollable
        val isEditable = node.isEditable
        val isCheckable = node.isCheckable
        val isChecked = node.isChecked
        val className = node.className?.toString()?.substringAfterLast('.') ?: "View"

        val isRelevant = isClickable || isScrollable || isEditable || isCheckable ||
                !text.isNullOrBlank() || !contentDesc.isNullOrBlank()

        if (isRelevant && elements.size < Constants.MAX_UI_ELEMENTS) {
            val id = nextId()
            val element = UIElement(
                id = id,
                className = className,
                text = text,
                hint = if (isEditable && text.isNullOrBlank()) node.hintText?.toString() else null,
                contentDesc = contentDesc,
                resourceId = resourceId,
                bounds = listOf(bounds.left, bounds.top, bounds.right, bounds.bottom),
                clickable = isClickable,
                editable = isEditable,
                scrollable = isScrollable,
                checkable = isCheckable,
                checked = isChecked
            )
            elements.add(element)
            nodeMap[id] = AccessibilityNodeInfo.obtain(node)
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            traverseNode(child, elements, nextId)
            child.recycle()
        }
    }

    private fun findScreenTitle(root: AccessibilityNodeInfo): String? {
        if (!root.text.isNullOrBlank()) return root.text.toString()
        for (i in 0 until root.childCount) {
            val child = root.getChild(i) ?: continue
            val resId = child.viewIdResourceName
            if (resId != null && (resId.contains("title") || resId.contains("toolbar"))) {
                val text = child.text?.toString()
                child.recycle()
                if (!text.isNullOrBlank()) return text
            } else {
                child.recycle()
            }
        }
        return null
    }

    private fun capElements(elements: List<UIElement>): List<UIElement> {
        if (elements.size <= Constants.MAX_UI_ELEMENTS) return elements
        val actionable = elements.filter { it.clickable || it.editable || it.scrollable }
        val textOnly = elements.filter { !it.clickable && !it.editable && !it.scrollable }
        val remaining = Constants.MAX_UI_ELEMENTS - actionable.size
        return actionable + textOnly.take(remaining.coerceAtLeast(0))
    }

    private fun emptyScreenState() = ScreenState(
        packageName = "unknown",
        timestamp = System.currentTimeMillis() / 1000,
        elements = emptyList()
    )

    // ── Action Execution ────────────────────────────────────────────

    fun executeTap(elementId: Int): Boolean {
        val node = nodeMap[elementId] ?: run {
            Log.w(TAG, "tap: element $elementId not found in node map")
            return false
        }
        return node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
    }

    fun executeType(elementId: Int, text: String): Boolean {
        val node = nodeMap[elementId] ?: run {
            Log.w(TAG, "type: element $elementId not found in node map")
            return false
        }
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    fun executeBack(): Boolean {
        return performGlobalAction(GLOBAL_ACTION_BACK)
    }

    fun executeHome(): Boolean {
        return performGlobalAction(GLOBAL_ACTION_HOME)
    }

    fun executeOpenApp(packageName: String): Boolean {
        return try {
            val intent = packageManager.getLaunchIntentForPackage(packageName)
            if (intent != null) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                startActivity(intent)
                true
            } else {
                Log.w(TAG, "open_app: no launch intent for $packageName")
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "open_app failed", e)
            false
        }
    }

    suspend fun executeScrollDown(): Boolean {
        return dispatchSwipeGesture(
            startX = resources.displayMetrics.widthPixels / 2f,
            startY = resources.displayMetrics.heightPixels * 0.7f,
            endX = resources.displayMetrics.widthPixels / 2f,
            endY = resources.displayMetrics.heightPixels * 0.3f,
            durationMs = 300L
        )
    }

    suspend fun executeScrollUp(): Boolean {
        return dispatchSwipeGesture(
            startX = resources.displayMetrics.widthPixels / 2f,
            startY = resources.displayMetrics.heightPixels * 0.3f,
            endX = resources.displayMetrics.widthPixels / 2f,
            endY = resources.displayMetrics.heightPixels * 0.7f,
            durationMs = 300L
        )
    }

    private suspend fun dispatchSwipeGesture(
        startX: Float, startY: Float,
        endX: Float, endY: Float,
        durationMs: Long
    ): Boolean = suspendCancellableCoroutine { cont ->
        val path = Path().apply {
            moveTo(startX, startY)
            lineTo(endX, endY)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, durationMs)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()

        val dispatched = dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                if (cont.isActive) cont.resume(true)
            }
            override fun onCancelled(gestureDescription: GestureDescription?) {
                if (cont.isActive) cont.resume(false)
            }
        }, null)

        if (!dispatched && cont.isActive) {
            cont.resume(false)
        }
    }

    fun executeScrollOnNode(elementId: Int, forward: Boolean): Boolean {
        val node = nodeMap[elementId] ?: return false
        val action = if (forward) {
            AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
        } else {
            AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        }
        return node.performAction(action)
    }
}
