import { marked } from "marked";
import DOMPurify from "dompurify";

export function formatMarkdown(content) {
  return DOMPurify.sanitize(marked.parse(content || "", { breaks: true, gfm: true }));
}

export function messagePreview(content) {
  return new DOMParser().parseFromString(formatMarkdown(content), "text/html").body.textContent || "";
}
