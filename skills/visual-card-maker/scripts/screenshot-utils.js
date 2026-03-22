/**
 * Screenshot Utils - 截图工具集
 * 提供 HTML 内容区域截图下载和复制到剪贴板功能
 * 依赖：html2canvas 库
 */

/**
 * 截图配置
 * @param {string} target - 目标元素选择器（默认 '.card-wrapper'）
 * @param {number} scale - 截图缩放比例（默认 2，即 2x 高清）
 * @param {string} filename - 下载文件名前缀（默认 'info-card'）
 * @param {string} bgColor - 背景颜色（默认 '#F1F0EC'）
 */
const SCREENSHOT_CONFIG = {
  target: '.card-wrapper',
  scale: 2,
  filename: 'info-card',
  bgColor: '#F1F0EC'
};

/**
 * 生成 Canvas 对象
 * @returns {Promise<HTMLCanvasElement>}
 */
async function generateCanvas() {
  return await html2canvas(document.querySelector(SCREENSHOT_CONFIG.target), {
    scale: SCREENSHOT_CONFIG.scale,
    useCORS: true,
    backgroundColor: SCREENSHOT_CONFIG.bgColor
  });
}

/**
 * 下载图片到本地
 * 生成 PNG 格式图片并自动下载
 */
async function downloadImage() {
  const btn = event.currentTarget;
  const span = btn.querySelector('span');

  btn.classList.add('loading');
  span.textContent = '生成中...';

  try {
    const canvas = await generateCanvas();
    const link = document.createElement('a');
    link.download = `${SCREENSHOT_CONFIG.filename}-${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();

    span.textContent = '已下载';
    setTimeout(() => {
      btn.classList.remove('loading');
      span.textContent = '下载图片';
    }, 1500);
  } catch (e) {
    console.error('下载失败:', e);
    span.textContent = '下载失败';
    setTimeout(() => {
      btn.classList.remove('loading');
      span.textContent = '下载图片';
    }, 2000);
  }
}

/**
 * 复制图片到剪贴板
 * 将截图作为 PNG 图片复制到系统剪贴板
 * 注意：需要 HTTPS 或 localhost 环境
 */
async function copyToClipboard() {
  const btn = event.currentTarget;
  const span = btn.querySelector('span');
  const icon = btn.querySelector('i');

  btn.classList.add('loading');
  span.textContent = '生成中...';

  try {
    const canvas = await generateCanvas();
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));

    await navigator.clipboard.write([
      new ClipboardItem({ 'image/png': blob })
    ]);

    btn.classList.remove('loading');
    btn.classList.add('success');
    icon.className = 'fa-solid fa-check';
    span.textContent = '已复制';

    setTimeout(() => {
      btn.classList.remove('success');
      icon.className = 'fa-solid fa-clipboard';
      span.textContent = '复制到剪贴板';
    }, 2000);
  } catch (e) {
    console.error('复制失败:', e);
    btn.classList.remove('loading');

    if (e.name === 'NotAllowedError') {
      span.textContent = '请允许剪贴板权限';
    } else {
      span.textContent = '复制失败';
    }

    setTimeout(() => {
      span.textContent = '复制到剪贴板';
    }, 2500);
  }
}

/**
 * 初始化截图工具栏
 * 自动创建截图按钮并添加到页面
 */
function initScreenshotToolbar() {
  // 检查是否已存在工具栏
  if (document.querySelector('.screenshot-toolbar')) return;

  const toolbar = document.createElement('div');
  toolbar.className = 'screenshot-toolbar';
  toolbar.innerHTML = `
    <button class="screenshot-btn" onclick="downloadImage()">
      <i class="fa-solid fa-download"></i><span>下载图片</span>
    </button>
    <button class="screenshot-btn secondary" onclick="copyToClipboard()">
      <i class="fa-solid fa-clipboard"></i><span>复制到剪贴板</span>
    </button>
  `;

  document.body.appendChild(toolbar);
}

// 页面加载完成后自动初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScreenshotToolbar);
} else {
  initScreenshotToolbar();
}
