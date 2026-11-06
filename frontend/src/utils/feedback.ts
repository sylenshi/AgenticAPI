/* 全局反馈工具：确认弹窗与剪贴板复制的统一封装 */
import { Message, Modal } from '@arco-design/web-vue'

/** 确认弹窗，resolve(true) 表示用户点击了确认 */
export function confirmDialog(
  content: string,
  title = '操作确认',
  okText = '确定',
  danger = false,
): Promise<boolean> {
  return new Promise((resolve) => {
    Modal.confirm({
      title,
      content,
      okText,
      cancelText: '取消',
      okButtonProps: danger ? { status: 'danger' } : undefined,
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
      // 点遮罩 / ESC 关闭时也要 resolve，否则调用方 `if (!confirmed) return` 之后静默卡死
      onClose: () => resolve(false),
    })
  })
}

/** 复制文本到剪贴板并轻提示 */
export function copyText(text: string, tip = '已复制') {
  navigator.clipboard.writeText(text)
  Message.success(tip)
}
