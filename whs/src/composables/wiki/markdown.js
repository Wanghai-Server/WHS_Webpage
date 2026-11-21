/**
 * 维基 Markdown 渲染入口（兼容层）。
 *
 * 渲染管线已统一到全站 composables/markdown/renderer.js：
 * - 统一 markdown-it 配置 { html:false, linkify:true, breaks:true }（防 XSS）；
 * - colorCodes、LaTeX（$...$ / $$...$$）、mermaid、代码高亮占位、媒体渲染、
 *   标题 id 与目录收集都在共享管线中实现；
 * - 本文件只保留 Wiki 专属的目录树组装逻辑。
 */
import { siteMarkdown } from '../markdown/renderer'

// 维基页面渲染入口（与全站共用同一套解析器 / 插件）
export const wikiMarkdown = siteMarkdown

/**
 * 把扁平目录组装成标题树（h1–h6 层层递进）。
 *
 * 规则：同级标题互成兄弟；下一个标题级别更深时挂为当前节点的子节点；
 * 级别回退（含跳级，如 h3 之后直接出现 h1）时回到对应祖先层级。
 * 首个标题不一定是 h1（如页面以 ## 开头），此时它自己就是树的根。
 *
 * @param {Array<{level:number,text:string,id:string}>} items 渲染时收集的扁平目录
 * @returns {Array<{level:number,text:string,id:string,children:Array}>} 树根节点数组
 */
export function buildOutlineTree(items) {
  const roots = []
  // 栈中保存当前祖先链（每项含 level 与 children）
  const stack = []
  for (const item of items || []) {
    const node = { ...item, children: [] }
    // 弹出级别不低于当前标题的祖先：同级（新兄弟）或更深（回退）都回到父级
    while (stack.length && stack[stack.length - 1].level >= node.level) stack.pop()
    if (stack.length) stack[stack.length - 1].children.push(node)
    else roots.push(node)
    stack.push(node)
  }
  return roots
}
