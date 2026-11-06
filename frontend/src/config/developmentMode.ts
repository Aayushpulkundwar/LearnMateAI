/** A UI convenience only; server authentication is never bypassed. */
export const shouldSkipLogin = (isDevelopment: boolean, requestedValue?: string): boolean =>
  isDevelopment && requestedValue === 'true';
