/* Shared legibility check: every visible text node that contains Chinese must render at >= 12px.
 * Pure Latin decorative labels may stay at 10px. Mixed labels count as Chinese.
 */
async function smallChinese(page, minPx = 12) {
  return page.evaluate((min) => {
    const cjk = /[㐀-鿿豈-﫿]/;
    const found = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const text = node.textContent.trim();
      if (!text || !cjk.test(text)) continue;
      const el = node.parentElement;
      if (!el || el.closest('script,style,noscript,template,[hidden],[aria-hidden="true"]')) continue;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
      const rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height) continue;
      const size = parseFloat(style.fontSize);
      if (size < min) found.push({ text: text.slice(0, 40), font: style.fontSize, tag: el.tagName.toLowerCase(), cls: el.className && String(el.className).slice(0, 40) });
    }
    return found;
  }, minPx);
}
module.exports = { smallChinese };
