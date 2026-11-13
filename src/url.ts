// The site is served under a base path (/primitive-bytes/ on GitHub Pages), so every
// internal link goes through here instead of starting with a bare "/".
export function url(path: string = '/'): string {
	const base = import.meta.env.BASE_URL.replace(/\/$/, '');
	return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}
