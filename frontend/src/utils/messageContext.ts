/**
 * 会话上下文工具 —— 保证只有「真正的对话内容」进入模型请求。
 *
 * 历史版本曾把截图元信息写进消息 content：
 *   "> 📷 屏幕截图 · 2560×1440 · 6.1s · 模型 deepseek-flash\n\n<答案>"
 * 这些行纯粹是界面装饰，既不该计入上下文，也不该每轮重复发送。
 * 新消息已改由 Message.meta 字段承载（只渲染、不发模型），
 * 这里负责把 localStorage 里老数据残留的那一行剥掉。
 */

/** 旧版截图元信息行：Markdown 引用 + 紧随其后的空行 */
const LEGACY_SCREENSHOT_META = /^> 📷 屏幕截图 ·[^\n]*\n+/

/** 把一条消息的 content 转成可安全发给模型的上下文文本 */
export function toContextContent(content: string): string {
  return content.replace(LEGACY_SCREENSHOT_META, '')
}
