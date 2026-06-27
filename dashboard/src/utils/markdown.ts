/** Strip HTML comments (e.g. <!-- profile_len=... -->) from markdown for display. */
export function stripMarkdownComments(md: string): string {
  return md.replace(/<!--[\s\S]*?-->/g, '').trim()
}
