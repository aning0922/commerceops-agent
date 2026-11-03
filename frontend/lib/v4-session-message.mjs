// These messages describe the current session only; they never settle an operation receipt.
export function sessionFailureMessage(status, code, outcome, hadSession) {
  if (outcome === 'REJECTED' && status === 401 && code === 'EXPIRED') {
    return '演示会话已到期，请重新开始新的演示空间。';
  }
  if (outcome === 'REJECTED' && status === 401 && code === 'SESSION_INVALID') {
    return hadSession ? '当前会话已失效，请重新开始演示。' : '';
  }
  if (outcome === 'REJECTED' && status === 403) {
    return '当前会话无法访问该演示空间，请检查权限或联系管理员。';
  }
  return '当前身份暂时无法验证，请稍后重新核对会话。';
}

// Only a previously verified session is eligible for automatic revalidation.
export function shouldRevalidate(knownSession, visible, online, pending) {
  return knownSession === true && visible === true && online === true && pending === false;
}
