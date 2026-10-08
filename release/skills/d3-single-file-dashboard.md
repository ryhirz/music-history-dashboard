---
name: d3-single-file-dashboard
description: 构建单文件 HTML 的 D3.js 交互式数据看板（尤其是通过 CDN 引入 D3 的离线/弱网场景），以及在无法人工看浏览器时用 headless Edge 自动验证图表真实渲染。当出现这类症状时使用：页面打开后图表区空白或长时间白屏（CDN 慢/被墙）；折线只画了一半、后半段凭空消失；误差带/面积色带整体不见或时有时无；切换到别的标签页再回来图表就残缺；面积图左右两端出现突兀的竖直线；数据点/标注框在某些窗口宽度下跑到画布外或被裁掉；图表上的文字标签互相压叠、或标签被粗线盖住读不出（数据点挤成一簇时标签更明显）；hover 浮层显示的数值属于**另一个数据点**（张冠李戴、右半区永远命中最后一个点）；窄屏下 Tooltip 整块跑到屏幕外看不见；以及任何"代码看着对但图不对"的 D3 渲染问题。也适用于给图表加误差带、注释浮层、残缺数据标记、入场动画、散点自动标签避让等常见需求，以及为图表写自动化几何断言（元素计数 / 线宽映射 / 越界检测 / 标注零重叠）。**当看板从"一张图"长成"一篇多区块长页数据新闻"时同样适用**：加悬浮/吸顶目录与滚动高亮（scroll-spy）、章节间过渡留白、跨区块叙事联动（穿针引线）、底部方法论/数据诚实声明区块、以及把整页打包成**完全离线的单文件**（内联 D3、断网对照验证、双形态交付）。当出现这类症状时也要用：滚动时页面卡顿掉帧；目录高亮不跟手或总是慢半拍；离线打开后图表全白（原来依赖 CDN）；无头浏览器里 scrollTo 或滚动相关逻辑"完全不生效"（实为 headless 下 scrollTo 无效 + rAF 在虚拟时间耗尽前不触发）；改了页面后回归测试报一堆 FAIL 其实是上一阶段的过期断言。即使用户只说"图没出来""刷新一下就好了""窄屏错位""面积图有奇怪的竖线""提示框数值不对""标签叠在一起看不清""做个目录""要能离线打开"也应触发本 skill。
author: agent
agent_created: true
---

# 单文件 D3 看板：渲染健壮性与无头验证

## 一句话核心

**D3 的动画全部由 `requestAnimationFrame` 驱动；一旦 rAF 被节流（切标签页、系统休眠、后台标签），未结束的 transition 会停在中间状态，且 `on('end')` 永不触发——图表会永久残缺，刷新才能恢复。凡是"靠动画收尾来设置终态"的写法都是定时炸弹。**

---

## 一、CDN 引入 D3：不要用同步 script 标签

### 症状
用户打开页面，图表区空白十几秒；或在网络受限环境（中国大陆）直接看不到图。

### 原因
`<script src="https://d3js.org/d3.v7.min.js"></script>` 是同步阻塞的。实测（国内网络）：

| 源 | 耗时 |
|---|---|
| `d3js.org` | **15.4 s** |
| `cdn.jsdelivr.net/npm/d3@7` | **4.2 s** |

规范/教程里常指定第一个源，直接照抄就会白屏十几秒。

### 标准做法
异步加载 + 超时切换，谁先到用谁；全部失败时页面正文仍完整可读，只让图表区显示错误卡片。

```html
<!-- 提前建连，省掉首次 TLS 握手 -->
<link rel="preconnect" href="https://d3js.org" crossorigin>
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>

<script>
(function(){
  var SOURCES = [
    'https://d3js.org/d3.v7.min.js',              // 规范指定源
    'https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js'  // 国内更快的镜像
  ];
  var TIMEOUT_MS = 2500;
  var settled = false, callback = null;

  function finish(ok){
    if (settled) return;
    settled = true;
    if (callback) callback(ok);
  }
  function attempt(i, isFallback){
    if (i >= SOURCES.length) { finish(false); return; }
    var el = document.createElement('script');
    el.src = SOURCES[i];
    el.async = true;
    el.onload  = function(){ finish(true); };
    el.onerror = function(){ attempt(i + 1, true); };
    document.head.appendChild(el);
    // 只对主源设超时：超时不取消它（可能马上就返回），而是并行拉镜像
    if (!isFallback){
      setTimeout(function(){ if (!settled) attempt(i + 1, true); }, TIMEOUT_MS);
    }
  }
  window.__onD3Ready = function(fn){
    if (settled) fn(true); else callback = fn;
  };
  attempt(0, false);
})();
</script>
```

主脚本改为注册回调，不要直接写裸代码：

```js
window.__onD3Ready(function(ok){
  if (!ok || typeof d3 === 'undefined'){
    chartEl.innerHTML = '<div class="fallback">D3.js 未能加载，请检查网络后刷新。</div>';
    return;
  }
  render();
  // …ResizeObserver 等
});
```

图表容器内先放一个"加载中"占位，首次渲染时移除，避免白屏期一片死寂。

> **注意**：`<script>` 内联代码的注释里**不要写 `<script src>` 这种字样**，会干扰基于正则的语法检查工具提取 script 块（浏览器本身能正确解析，但工具会误判）。

---

## 二、动画终态必须由定时器兜底（本 skill 最重要的一条）

### 症状（三个往往同时出现）
- 折线只画了一半，后半段消失
- 误差带/面积色带整体不见，或时有时无
- 数据点只显示前一部分
- "切到别的标签页再回来就残缺了"

### 根因
`d3.transition()` 由 rAF 驱动。rAF 在后台标签页会被节流到几乎不触发，系统休眠时完全停摆。此时：

- `stroke-dasharray` 描边动画停在中间 → **线被永久截断**
- `opacity` 被冻结在中间值 → **色带/点不可见**
- `.on('end')` 回调永不执行 → **清不了 dasharray**

### 标准做法：`interrupt()` + 定时器硬复位

```js
const settleAll = () => {
  // ⚠️ 必须先 interrupt()：被冻结的 transition 仍然"活着"，
  //    rAF 一恢复就会用插值中间值覆盖下面写的终态。
  [bandPath, linePath, tailPath, halo, leader].forEach(sel => sel.interrupt());
  pts.interrupt();

  linePath.attr('stroke-dasharray', null).attr('stroke-dashoffset', null);
  bandPath.attr('opacity', 1);
  pts.attr('opacity', 1);
  // …
};

// 定时器走真实时钟，不受 rAF 节流影响
setTimeout(settleAll, ANIM_MS + 900);
```

另外永远尊重系统偏好：

```js
const reduceMotion = window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (isIntro && !reduceMotion) { /* 播动画 */ setTimeout(settleAll, ANIM_MS + 900); }
else { settleAll(); }
```

**入场动画只能在首次渲染播一次**，resize 重绘时直接落终态（用 `isIntro` 标记），否则每次缩放窗口都重播一遍。

---

## 三、CSS `transition` 同样不可信，改用"失败安全"的 animation

### 症状
用 `transition: opacity .35s` + `setTimeout` 延迟显示的注释框，帧里显示为半透明/几乎看不清。

### 标准做法
默认写成可见，再用 `animation` + `fill-mode: both` 做揭示——**动画不执行时元素依然完整可读**：

```css
.anno{
  opacity: 1;                    /* 失败安全：动画不跑也可见 */
  transform: translateX(-50%);   /* 居中交给 CSS，别让 JS 和 CSS 抢 transform */
}
.anno.reveal{ animation: annoIn .45s ease 1.35s both; }
@keyframes annoIn{ from{ opacity:0 } to{ opacity:1 } }
```

**关键坑**：CSS animation 在层叠中**优先于 inline style**。想纠正只能移除动画类（`el.classList.remove('reveal')`），改 `el.style.opacity` 是无效的。

**另一个坑**：不要同时用 JS 设 `style.transform` 和 CSS 定义 `transform`，会互相覆盖。JS 只负责 `left/top`，`translateX(-50%)` 固定写在 CSS 里。

---

## 四、误差带（area）的两个数据/视觉陷阱

### 1. 上下界必须裁剪到有效值域
`mean ± 1σ` 会越出数据本身的定义域（如 acousticness ∈ [0,1]，而 0.80±0.32 → 上界 1.12）。不裁剪的话色带会画到坐标轴外，看起来像"数据溢出"。

```js
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const area = d3.area()
  .x(d => x(d.decade))
  .y0(d => y(clamp(d.mean - d.sd, 0, 1)))
  .y1(d => y(clamp(d.mean + d.sd, 0, 1)))
  .curve(d3.curveMonotoneX);
```

裁剪是**正确处理**，但要在图表下方注明"贴边处的色带被削平是边界挤压所致，非数据错误"，否则读者会以为画错了。

### 2. 面积路径的 `stroke` 会产生左右"封口线"
`d3.area` 生成的路径在首尾是闭合的。加描边后，图左右两端各出现一条竖直直线，看起来像数据被硬生生切断。

**解法**：`.attr('stroke', 'none')`，边界感完全交给渐变的透明度。

### 3. 插值曲线选 `curveMonotoneX`
平滑但不过冲，不会在数据点之间"甩"出假极值。`curveBasis` 会偏离真实数据，时间序列慎用。

---

## 五、标注浮层的定位：不要用固定偏移量

### 症状
注释框在宽屏正常，在窄屏跑到画布外、或被裁掉一半；引导线算成负坐标而看不见。

### 根因
用硬编码偏移（如 `y(point) - 106`）定位。当数据点本身靠近画布顶部（值接近 Y 轴上限）时，窄屏下 `y(point)` 可能只有 20 多像素，减固定值即得负数。

### 标准做法
1. **定位时兜底**：`top = Math.max(8, y(d.mean) + margin.top - OFFSET)`
2. **引导线用实测高度反推**，而非估算：
   ```js
   const annoBotCss = parseFloat(annoEl.style.top) + (annoEl.offsetHeight || 78);
   const leaderY2 = (annoBotCss - M.top) + 7;   // SVG 局部坐标
   ```
3. **水平方向 clamp 住**，防止框超出容器：
   ```js
   const half = (W < 640 ? 86 : 100) + 4;
   annoEl.style.left = clamp(x(d) + M.left, half, W - half) + 'px';
   ```
4. **给引导线留足长度**：端点间距小于 ~15px 时，虚线会退化成看不见的小点。宁可把注释框抬高一点。
5. **窄屏要主动扩大 top margin**，同时容纳"标注框 + 数据点 + 引导线"三者。

---

## 六、无头浏览器验证（没有 playwright 也能做）

Windows 上直接用系统自带的 Edge：

```bash
EDGE="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"

# ① 视觉验证 —— 一定加 --force-device-scale-factor=1
"$EDGE" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
        --force-device-scale-factor=1 \
        --window-size=1440,1600 --virtual-time-budget=15000 \
        --screenshot="E:\out.png" "file:///E:/path/page.html"

# ② 终态验证 —— 比截图可靠，能读到动画结束后的真实属性值
"$EDGE" --headless=new --disable-gpu --no-sandbox \
        --force-device-scale-factor=1 --window-size=1200,900 \
        --virtual-time-budget=25000 --dump-dom "file:///E:/path/page.html" > dump.html
```

### 必须知道的三个特性

1. **`--virtual-time-budget` 会加速 `setTimeout`，但不推进 rAF 驱动的 d3.transition。**
   这不是缺陷——它恰好让无头环境成为"rAF 被节流"的**天然测试场**，能主动逼出第 2 节的坑。如果这里渲染完整，真实浏览器更没问题。

2. **不加 `--force-device-scale-factor=1` 时，输出 PNG 尺寸 ≠ `--window-size`。**
   实测 `--window-size=1280,2300` 输出 1920×3450（DPR 1.5），按缩略图比例估算的裁剪坐标会全部错位，白白排查半天。**先打印 `Image.size` 再用比例换算裁剪框。**

3. **DOM 检查前必须先剔除 `<script>` 和 `<style>`。**
   否则 CSS 里的类名（如 `.fallback`、`.loading`）会造成大量假阳性：
   ```python
   body = re.sub(r'<script.*?</script>', '', raw.split('<body>',1)[1].split('</body>',1)[0], flags=re.S)
   ```

### 验证交互逻辑（hover / tooltip）
注入探针，dispatch 真实事件后把结果写进隐藏 div，再用 `--dump-dom` 抓取：

```js
setTimeout(function(){
  var out = document.createElement('div'); out.id = 'TT_PROBE';
  var target = document.querySelector('rect.overlay');
  var bb = target.getBoundingClientRect();
  target.dispatchEvent(new MouseEvent('mousemove', {
    clientX: bb.left + bb.width * 0.5, clientY: bb.top + bb.height * 0.5,
    bubbles: true, cancelable: true
  }));
  out.textContent = document.getElementById('tooltip').textContent.replace(/\s+/g,' ');
  document.body.appendChild(out);
}, 4000);
```

> **定位目标的技巧**：按容器比例估算坐标容易偏（overlay 有负偏移、scalePoint 有 padding）。**直接读目标数据点的 `getBoundingClientRect()`** 更准。
> 若某个分支始终命中不到，而它是纯数据驱动的模板分支，直接调用渲染函数（写成全局函数即可）传入目标数据验证，比反复调坐标高效。
>
> ⚠️ **但更好的锚点是 x 轴刻度，不是数据点。** 数据点的 bbox 中心 = `g的屏幕左边界 + x(decade)`，是**客户端**坐标；而 handler 内部 `nearestPair` 比较的是 **g 本地**坐标。两者差一个 `g` 的偏移量，只有 handler 的坐标换算正确时才等价——一旦换算坏了（见第七节），用 bbox 反推就会得到"差一格 / 差四格"的假象，把你引向错误的方向。**刻度的 `<g transform="translate(tx,0)">` 里的 `tx` 就是 g 本地的 `x(decade)`，是唯一无歧义的真值锚点**：

```js
// 用刻度 transform 的 tx 作为 g 本地坐标基准，逐个 decade 验证命中
var ticks = document.querySelectorAll('#chart-meso .x-axis text');
var tx = {};   // '1970s' -> 433.5（g 本地坐标）
for (var i = 0; i < ticks.length; i++) {
  var tr = ticks[i].parentNode.getAttribute('transform');
  tx[ticks[i].textContent.trim()] = parseFloat(tr.match(/translate\(([-\d.]+)/)[1]);
}
```

> **验证交互命中的正确姿势不是"看坐标对不对"，而是"逐项断言命中了哪一条数据"**——把每个刻度都点一遍，断言 tooltip 报出的年代 == 该刻度，全对才算过。坐标算错时最典型的指纹是：**右半区永远命中最后一个点**（因为绝对坐标超出了 scale 的值域而饱和），而左半区整体右移。

### 无头截图与坐标测量的三个新坑（实测）

1. **`--screenshot` 与 `--dump-dom` 不能在同一次调用里给。** 同时给会静默地只产出 DOM、PNG 完全不生成（且退出码仍是 0，`stat` 才会发现文件不存在）。**拆成两次调用。**
2. **`--screenshot="相对路径"` 不生效**，必须给绝对 Windows 路径：`--screenshot="E:\out\%NAME%.png"`。
3. **`--window-size` ≠ 布局视口宽度。** 实测 `--window-size=460` 时 `window.innerWidth === 478`——布局视口**比窗口还宽**，截图会从右侧裁掉内容。要给极窄宽度，把窗口调大一点（如 `--window-size=500`）再按 `innerWidth` 裁左侧。
4. **带 `vh` 单位的页面，几何量测必须与截图用同一个 `--window-size`（含高度）。** 同一页面 `--window-size=1440,6200` 量到 `sec-meso top=0 h=1775`，换成 `1440,1900` 结果一样，但**截图那次如果高度不同、页面又用了 `100vh`，区块位置就会整体平移**，按旧坐标裁剪会全部错位。**最省事的做法：把几何探针与截图用完全相同的 `--window-size`，或干脆做一个"只保留目标区块"的隔离页：**

```js
// 隔离页：隐藏其它区块，目标区块从 y=0 开始 → 裁剪坐标可预测
document.querySelectorAll('.panel').forEach(el => {
  if (el.id !== 'sec-meso') el.style.display = 'none';
});
// 顺便把 header/nav/footer 一起藏掉，避免它们把区块往下推
['header','nav','footer','.hero'].forEach(sel =>
  document.querySelectorAll(sel).forEach(el => el.style.display = 'none'));
```

隔离后仍要用一次 `--dump-dom` 读出区块自身的 `getBoundingClientRect()`，把 `top/height` 写进页面上的隐藏节点（`opacity:.01`），裁剪脚本直接读它，比手算可靠。

### ⭐⭐ 坑中之坑：`--virtual-time-budget` 下 **rAF 在脚本执行期间不触发**

这是"用无头浏览器驱动滚动/交互"时最容易被误判成全盘失效的一条。**一次踩了两层：**

| 层 | 现象 | 根因 |
|---|---|---|
| 1 | `window.scrollTo(0, y)` 后 `window.pageYOffset` **恒为 0** | headless 没有真实的滚动容器合成，`scrollTo` 静默无效（不报错） |
| 2 | 页面里打的 rAF 标记读到 `raf=0`，但 `--dump-dom` 出来的 HTML 里**却有 `RAF_FIRED`** | `requestAnimationFrame` 回调要等**虚拟时间预算耗尽、快照那一刻才补跑**——输出里有，但读到它时它还没跑 |

**为什么致命**：性能好的页面，滚动相关的重算基本都跑在 rAF 里（这是正确做法）。
于是"用真实滚动去驱动测试"必然什么都测不到 → **误判成功能全盘失效**，然后去改本来没问题的代码。

**解法：把「逻辑正确性」与「环境真实性」分层测，各测各的**

层 1 — 测逻辑（探针内做桩，不掺环境噪声）：

```js
/* 把滚动位置与 rAF 都换成可手动推进的桩 */
var _y = 0;
function setY(y){
  _y = y;
  try { window.scrollTo(0, y); } catch(e){}
  try { Object.defineProperty(window, 'pageYOffset',
        { get: () => _y, configurable: true }); } catch(e){}
  try { Object.defineProperty(document.documentElement, 'scrollTop',
        { get: () => _y, configurable: true }); } catch(e){}
  window.dispatchEvent(new Event('scroll'));
  flushRaf();                 // 立刻把这次滚动引发的重算跑完
}

var rafQ = [], rafQTotal = 0;  // rafQTotal 可反向证明"页面确实在用 rAF"
window.requestAnimationFrame = function(fn){ rafQ.push(fn); rafQTotal++; return rafQ.length; };
window.cancelAnimationFrame  = function(h){ if (h > 0 && h <= rafQ.length) rafQ[h-1] = null; };
function flushRaf(){ var q = rafQ; rafQ = []; q.forEach(fn => fn && fn(performance.now())); }
```

层 2 — 测真机表现（另起一次 `--screenshot`，**不要**在同一进程里靠 `scrollTo` 摆位）：
截图走的是另一条渲染路径，**出图前 rAF 已完成**，所以能拍到终态。
要拍"滚到某一章"的画面，也别靠 `scrollTo`，直接**用 CSS 把前面区块 `display:none`** 把目标顶上来：

```python
def only_this(sid, *keep):
    css = ''
    for s in all_sections:
        if s != sid: css += '#%s{display:none !important;} ' % s
    return css + '\n#%s{margin-top:0 !important;} ' % sid
```

**判断口诀**：无头里"什么都是坏的"→ 先怀疑驱动方式（scrollTo / rAF），别急着改业务代码。

### ⭐ 跨阶段跑全量回归时：一条 FAIL 先问「代码错了，还是断言的期望值过期了」

多阶段迭代的页面，**上一阶段的校验脚本会带着过期的期望值活下来**，然后在下一次全量回归时报一堆 FAIL，
看起来像"新改动破坏了老功能"，实际是**断言自己没跟上**。实测遇到的四条：

| 断言原话 | 旧期望 | 现状（正确） |
|---|---|---|
| `loadingEl.remove()` 次数 | 4 | **6** |
| fallback 覆盖容器 | 5 个 | **7 个** |
| footer 文案 | `Phase 3` | `Phase 5`（本就要求更新） |
| 某区块「仍为 placeholder」 | 是 | **已升级为正式区块** |

**排查动作**：逐条去 `grep` 断言原文，看清它到底在断言什么状态；
**修法**：改成对着**当前正确状态**写，并在注释里写清**为什么变**（否则下一个人还会当成回归）。
同时可以顺手补两条**前瞻断言**（断言"已完成升级"而非"仍是旧态"）。

⚠️ 数数别数错对象：上表第一条，**7 个是「图表容器」数，6 个才是「loading 节点」数**
——其中有个容器只是往父容器里 `append` 一个子 SVG，没有自己的 loading 节点。
**断言要对着被数的那个东西写。**

### 内联 JS 语法检查
正则提取 `<script>` 块 → 逐个 `node --check`。注意非贪婪匹配 `(.*?)</script>`，并跳过带 `src` 的标签。

### 注解碰撞检测：把"文字压字/压点"变成可复算的几何断言
肉眼看截图判断"这里好像叠了"既不可靠也不可回归。做法：从 `--dump-dom` 的结果里抽 `<text>`，
估算包围盒，两两求交。

```python
# 宽度估算：CJK/全角 ≈ 1.0 em，ASCII ≈ 0.55 em（略保守）
# 纵向：baseline 上方 0.78 em、下方 0.22 em
# text-anchor: start → x0=x; middle → x0=x-w/2; end → x0=x-w
```
要同时查两类碰撞，它们根因不同：
- **文字 × 文字**：长标题撞右上角角标（如 `Have Yourself a merry little Christmas` 撞 `n=47`）→ 修法是**标题自适应**（缩略表 → 降字号 → 截断加省略号），别只给当前这首打补丁。
- **文字 × 数据点**：解到"文字压住散点"。**只查前者会漏掉后者**——本项目就是先只查文字×文字（全过），
  截图放大后才发现副标题正骑在引导线上、还压着一个点。

⚠️ **两个必须处理的实现陷阱**：
1. **必须累积祖先 `translate()`**。分面图每个面板都有自己的 `translate`，不累积的话 10 个面板的文字
   会全部塌到同一处，报出几百个**假**重叠。
2. **`--dump-dom` 把 SVG 空元素序列化成 `<circle …></circle>`**（既有开标签也有闭标签，**不是** `/>`）。
   所以解析时：只有 `svg`/`g` 这类**容器**参与压栈弹栈，`circle`/`text`/`line`/`rect`/`path` 一律当**叶子**
   并忽略其闭标签。否则每个圆点被数两遍，`</circle>` 还会去弹栈、让后面所有元素的偏移全部错位
   （本项目就此误报过"文字压点"）。

**几何断言跑通后，仍要抽 2–3 处放大截图人工确认**——自动检测只能证明"框不相交"，
证明不了"标注离它指的那个点不远"。

### ⚠️ 只有这三类碰撞都查了，才算查全（实测：只查前两类会漏掉最刺眼的那种）

| 类别 | 为什么必须查 | 典型症状 |
|---|---|---|
| 文字 × 文字 | 长标题撞角标 | `Have Yourself a merry little Christmas` 撞 `n=47` |
| 文字 × 数据点 | 标注压住散点 = 信息丢失 | 副标题骑在引导线上并压住一个点 |
| **文字 × 线段** ⭐ | **线宽 8px 的粗线会把标题整个吃掉** | `1950s` 标签被断层段盖住，只剩"195…" |

第三类的修法：把每条路径按**它的实际 `stroke-width` 膨胀**成 AABB 带入代价函数，
并**按线宽加权**（越粗的段压上代价越高，如 `c += ox*oy*(2 + wt*0.9)`）——
这样算法宁可把标签推远，也不会让它落在粗线上。

### 宽度的口径：CJK 必须按全角算，否则全是误报
`len(t) * fs * 0.56` 把中文当半宽 → 中文标注宽度被低估近一半 → 重叠检测大面积漏报。
正确估算（可与 `getBBox` 对齐到 ±5%）：

```python
def text_width(t, fs):
    w = 0.0
    for ch in t:
        o = ord(ch)
        if (0x2E80 <= o <= 0x9FFF or 0xFF00 <= o <= 0xFF60 or
            0x3000 <= o <= 0x303F or o in (0x2014, 0x2192, 0x2190, 0xB7, 0x2212)):
            w += 1.0          # CJK / 全角 / — → ← · −
        elif ch == ' ':
            w += 0.3
        else:
            w += 0.56
    return w * fs * 1.04       # 4% 余量
```

### 断言口径错误：比"漏报"更浪费时间
自查三类常见错写（本项目实测各踩一次）：

| 错写 | 为什么错 | 正确写法 |
|---|---|---|
| `min(a, b) >= max(arr)` 判"这两项最大" | `max(arr)` 就是它们自己 → **恒不成立**，逻辑矛盾 | 判它们占据排序**前 N 名**：`set(sorted(range(n), key=..., reverse=True)[:2]) == {i, j}` |
| 比两张子图色块的**绝对像素宽度** | 两图各有**独立坐标系**（如 X 域一个是 `1→0`、一个是 `0→−0.8`），绝对像素本就不同 | 比**相对区间比例** `w / (maxX - minX)` |
| 多子图只检了主图的文字 | 副图完全没覆盖 | **每张子图各跑一遍**同样的文字碰撞断言 |

### ⚠️ 改完 HTML 必须删缓存 DOM 再诊断
`--dump-dom` 的产物会落盘复用。改完 HTML 却用旧 dump 做诊断，会读到**上一版的状态**，
把已经修好的问题当成没修（本项目被误导一次，白白多改一轮）。**标准动作**：
```bash
rm -f <workdir>/dom_*.html && python verify/render_check.py
```

### 期望值别写死：从数据源反算
元素计数、路径 `d`、参考线坐标这类断言，期望值应当**由同一公式在验证脚本里重算**，
或在 SQL 里算出（`count(*) WHERE thin_cell`），再与 DOM 比对。
比字符串更要比**数值**：DOM 属性是 JS float 的原始序列化（`translate(48.50000000000001,12)`），
和 Python 的短小数**永远不相等**，必须给容差（1e-6）。这类"假失败"很容易被误当成真 bug 去改代码。

---

## 七、交互命中的坐标系：`d3.pointer` 只能接 DOM 节点

### 症状
Tooltip 显示了**另一个 datapoint 的数据**——hover 1970s 的点，浮层里却是 2010s 的数值。没有报错、没有空白，数值本身完全合理，只是**张冠李戴**。这是最隐蔽也最严重的一类渲染缺陷：看板看起来在工作，但每个数字都被标错了对象。

### 根因：`append()` 返回的是 selection，不是 DOM 节点
```js
const svg = d3.select(el).append('svg');
const g   = svg.append('g').attr('transform', `translate(${M.left},${M.top})`);
//    ↑ 这是 d3 selection，不是 <g> 元素！
d3.pointer(ev, g);      // ❌ 静默降级成 [event.pageX, event.pageY]
d3.pointer(ev, g.node()); // ✅
```
`d3.pointer(event, node)` 内部依次尝试：`node.ownerSVGElement.createSVGPoint()` → `node.getBoundingClientRect()` → **兜底 `[event.pageX, event.pageY]`**。d3 selection 既没有 `ownerSVGElement` 也没有 `getBoundingClientRect`，于是两段都跳过，**悄无声息地**返回绝对页面坐标。

后果：`mx` 的值域变成 `[0, 视口宽度]`，而 `x()` 的值域是 `[0, iw]`。两者量纲不同，`nearestPair` 就会系统性地判错：
```
实测（1440 视口，iw≈824，g 屏幕偏移 283.6）
  d3.pointer(ev, g)      → mx = 717.0  ← 等于 clientX（绝对坐标）
  d3.pointer(ev, g.node()) → mx = 433.5  ← 正确的 g 本地 x(1970s)
```
- 左半区：整体**右移**（hover 1920s 报 1960s）
- 右半区：`mx` 超出 `x(domain)` 上限而**饱和**，永远命中最后一个点

### ⚠️ 第二层坑（更阴）：传了真 DOM 节点，但它是**带 x/y 的元素**

修好"别传 selection"之后**还会再错一次**。`d3.pointer` 内部走
`node.getScreenCTM().inverse()`，而 **`getScreenCTM()` 只含祖先 transform，不含元素自身的 `x` / `y`**。
所以第二参数若是 `<rect x="505">` 这种定位元素，解出来的是 **SVG 根坐标**，不是元素局部坐标。

```
实测（1440 视口，多面板小多图，命中区 <rect x="505" y="54">）
  rect 的 getBoundingClientRect().left = 728   ← 含 x=505
  但 rect.getScreenCTM().e             = 223   ← 只到 svg 左边缘，没加 505
  d3.pointer(ev, this)  → mx = 641.42   ← 期望 136.42，正好多出 505
```

**为什么 Phase 1/2 没踩到**：它们传的是 `g.node()`。`<g>` 自身没有 x/y，
而它的 `transform` **恰好就在 CTM 里**，所以是对的。→ 只有"定位元素自指"才中招。

**后果比第一层更坏**：第 0 列（x 很小）看起来大致正常，其余列 **整格 0→panelWidth 的横扫全部吸附到同一个末端刻度**——
实测 9 个采样点 `0:2010s 30:2010s 60:2010s … 210:2010s`，全错。

**修法：拿 svg 根坐标，再手工减掉面板偏移**（无 transform、无 x/y，最稳）：
```js
.on('mousemove', function(ev){
  const [px] = d3.pointer(ev, svg.node());        // SVG 根坐标系
  const mx = px - (M.left + c * (pw + gap));      // 手工换算成该面板的局部 x
  …
})
```
（另一条等价路线：把命中区 `<rect>` 放进面板 `<g>` 里、坐标写 `x=0`，再传 `this.parentNode`。）

**回归测试要和第一层一起做**：取**最右列**那一格（偏移最大，最灵敏），沿面板宽度等分 21 点横扫，断言——
① 21 点全部有吸附结果；② 左端 = 首刻度、右端 = 末刻度；③ 序列**单调不减**（有错位跳变说明坐标系又错了）；
④ `x(目标刻度)` 对应的那一点吸附到目标刻度。

### 定位手法：monkey-patch 抓真值
不要靠肉眼猜偏移量。在探针里包一层，直接把实参和返回值打出来：
```js
var _ptr = d3.pointer;
d3.pointer = function(ev, node){
  var r = _ptr.apply(this, arguments);
  trace.push('args=' + arguments.length
           + ' arg1=' + (arguments.length>1 ? (arguments[1] && arguments[1].nodeName) : '(缺省)')
           + ' clientX=' + ev.clientX + ' → mx=' + r[0]);
  return r;
};
```
判读要点：**`arg1.nodeName === undefined` 就是 selection 传进来了**（真实 DOM 节点会有 `'g'` / `'rect'`）。同理可包 `window.showTipMeso` 打出 handler 实际收到的 `p.decade`，一眼看出张冠李戴。

> ⚠️ 探针必须**等 d3 就绪后再插桩**。若 D3 走异步竞速加载器，脚本解析期 `d3` 还不存在，直接 `d3.pointer = ...` 会抛错并让整个探针静默失效。用轮询 / `window.__onD3Ready` 包住插桩。

### 回归测试：逐项断言命中
修完不要只看"现在对上了"，写成可重复的断言表——把每个刻度点一遍，比对 tooltip 报出的年代：
```
✔ hover 1920s → 报 1920s   ✔ hover 1930s → 报 1930s   …   ✔ hover 2020s → 报 2020s
命中率 = 11 / 11
```
三档宽度各跑一遍（1440 / 900 / 460），全 11/11 才算通过。这个测试对"右侧饱和"型缺陷尤其灵敏。

---

## 八、Tooltip 定位：翻边之后必须再夹一次

### 症状
宽屏正常，**窄屏下 Tooltip 整块跑到屏幕外**——`getBoundingClientRect().left` 是负数，内容完全看不见。

### 根因
只写了"右侧放不下就翻到光标左边"，但没管翻过去之后的边界：
```js
let left = ev.clientX + pad;
if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - pad;
// ↑ 翻边后 left 可能为负（窄屏 + 光标偏右）
```

### 标准做法
翻边逻辑后面**无条件再夹一次**：
```js
if (left + tw > window.innerWidth - 8) left = ev.clientX - tw - pad;
left = Math.max(8, Math.min(left, window.innerWidth - tw - 8));
if (top  < 8)                          top  = 8;
if (top + th > window.innerHeight - 8) top  = window.innerHeight - th - 8;
```
实测：460 视口下 1970s 的浮层从 `[-111, 226]` 修正为 `[8, 345]`。

### 验证
在探针里同时报 `left/right` 与 `window.innerWidth`，断言 `left >= 0 && right <= innerWidth`，**每个分支都测**（含内容最长的警示分支）。窄屏下浮层宽度可能逼近视口宽度，此时右边界贴齐是允许的，左边界为负则一定是缺陷。

---

## 九、分面图（small multiples）：多组 selection 的数据广播陷阱 ⭐

### 症状
10 张小图**每张都画了全部 10 条线**，叠成一团毛线：整体像"乱麻""噪声带"，
但**没有任何 JS 报错**，`node --check` 通过，数据也逐值正确。
如果每格的数据量小、或各条线形状相近，还可能只是"看着有点奇怪"而被放过去。

### 根因：多组 selection 上 `.data()` 会把数组**广播进每一个 group**
```js
const panels = svg.selectAll('g.sm').data(SONGS).enter()
    .append('g').attr('class', 'sm')                 // ← 10 个 group

const plot = panels.append('g').attr('transform', `translate(0,${PT})`);  // ← 又是 10 个 group

plot.append('g').selectAll('path').data(SONGS)       // ❌ 每组都被喂进完整 10 条
    .enter().append('path').attr('d', d => segPath(d));
// 结果 = 10 组 × 10 条 = 100 条 path，每张图都画全部歌曲
```
`selection.data(arr)` 的语义是**对每个 group 各做一次 join**。
`svg.selectAll('g.sm')` 只有 1 个 group（父是 svg），所以绑定 10 个面板是对的；
但 `plot` 有 **10 个 group**，再喂整份数组就变成 10× 广播。

同理，点集若写成"先把所有格摊平成一个数组、再喂给多组 selection"，每个面板就会画出全部点。

### 修法：用嵌套 join 的**父级数据形式**
```js
// ① 每组只要 1 个元素（线 / 参考线 / 环）
plot.append('g').selectAll('path.sm-solid').data(d => [d])   // ✅ 回调按 group 求值，拿到该面板的 datum
    .enter().append('path').attr('class', 'sm-solid').attr('d', d => segPath(d, false));

// ② 每组要该面板自己的子集（点）
dotG.selectAll('circle.sm-dot')
    .data(song => seriesOf(song).filter(s => s.cell && !s.cell.thin))   // ✅ 每组返回自己的子集
    .enter().append('circle').attr('class', 'sm-dot');
```

### 只有数 DOM 元素数才能抓到
源码 lint 抓不到（语法合法），数据校验也抓不到（值是错的**图**不是错的值）。**必须渲染后数元素**：
```
面板 = 10      实线路径 = 10      虚线路径 = 10
实心点 = 非薄格数      空心点 = 薄格数      参考线 = 10
```
期望值从数据源算出（如 `SELECT count(*) WHERE thin_cell`），**不要写死**。
数量对不上（尤其正好是 10 倍）就是广播。

> 顺带一个 lint 级守卫：统计 `.data(SONGS)` 出现次数。**它应当只出现 1 次**（绑面板那一次）；
> 出现第二次基本就是又喂进了多组 selection。

---

## 十、散点标签的自动避让：零空间处必须换策略 ⭐⭐

"给每个点加个年代标签"看着简单，实则是这张图最难的一环。**通用避让算法有一个隐含前提：存在自由空间。** 一旦点密到没有自由空间，无论怎么调参数都会失败。

### 症状（三档宽度只有一档通过，是典型信号）
- 1440px 全绿，900 / 478px 必压点或压线
- 加大搜索半径、降低距离惩罚…… 全都只是"把失败从 A 处挪到 B 处"

### 正确做法：分而治之

```
① 先找"零空间簇"——孤立看每个点的邻居距离，若 ≤ 2~3 倍字高，即为一簇
② 簇内标签【不逐个避让】，改为整体排版：
   · 竖排成一列（行距固定 ≈ 15px），整列垂直居中于簇心
   · 列的位置取"簇外最近的一侧空白带"（如簇最左侧 - 42px）
   · 每个标签拉一条细虚线引线回自己的点（否则读者认不出归属）
   · 保留语义色（如异常年仍用警示橙），不要因为排版统一就丢掉编码
③ 簇外的稀疏点，才交给通用避让
```

### 通用避让的实现要点（用于稀疏区）

```js
// 代价函数：三类障碍物、三档权重
const costOf = box => {
  let c = 0;
  for (const o of textObs){          // 文字/注释块 → 膨胀 2.5px（紧贴也糊）
    const P = 2.5;
    const ox = Math.min(box.x1+P, o.x1+P) - Math.max(box.x0-P, o.x0-P);
    const oy = Math.min(box.y1+P, o.y1+P) - Math.max(box.y0-P, o.y0-P);
    if (ox > 0 && oy > 0) c += ox * oy;
  }
  for (const o of dotObs){           // 别的数据点 → 不膨胀，但重罚
    const ox = Math.min(box.x1, o.x1) - Math.max(box.x0, o.x0);
    const oy = Math.min(box.y1, o.y1) - Math.max(box.y0, o.y0);
    if (ox > 0 && oy > 0) c += ox * oy * 6;
  }
  for (let i = 0; i < segBands.length; i++){   // 路径 → 按线宽加权
    const o = segBands[i];
    const ox = Math.min(box.x1, o.x1) - Math.max(box.x0, o.x0);
    const oy = Math.min(box.y1, o.y1) - Math.max(box.y0, o.y0);
    if (ox > 0 && oy > 0) c += ox * oy * (2 + widthOf(i) * 0.9);
  }
  return c;
};
```

**两轮搜索**：第一轮 12 个常规方位（`起始/结束 × 上/下 × 近/中/远`），零代价立即采用；
第二轮（兜底）绕点做**环形细搜**（半径 24→190px 步进 6、每圈 40 个角度、**竖向压扁 0.55** 以贴合文字行高），
并**否决越出绘图区**的位置。

⚠️ **自身那个点必须从障碍物里排除**——标签本来就是贴着点放的，否则算法会为了"躲开自己"把标签推到荒唐位置。

### 验证：文案框的"可读性"也要断言
不要只查"框不相交"。本项目实测：**框不相交、但文字正压在 8px 粗的橙色段上**，肉眼完全读不出。
所以断言要包含「文字 × 线段」这一类（见第六节「只有这三类碰撞都查了，才算查全」）。

---

## 十一、多区块长页：导航、跨区联动与离线打包

当单文件看板从"一张图"长成"一篇数据新闻"（多个叙事区块纵向排列）时，会多出一类**只有长页才有**的需求与坑。

### 12.1 目录与滚动高亮（scroll-spy）

**定位用 `position:fixed`，不要用 `sticky`。** 图表容器常带 `overflow` 上下文，`sticky` 的吸附行为会被影响；`fixed` 不受任何祖先 overflow 影响，行为可预测。

**滚动监听的三条性能纪律**（长页必须有）：
```js
var pending = false;
function schedule(){
  if (pending) return;                       // ① 合并：一帧只排一次
  pending = true;
  requestAnimationFrame(function(){
    pending = false;
    /* ② 回调里【只做写】，所有读布局推迟到这里，且每帧最多读一次 */
    ...
  });
}
window.addEventListener('scroll', schedule, { passive: true });  // ③ passive：不阻塞滚动合成
```

**高亮判定不要用 IntersectionObserver 的 ratio。** 长页各区块高度差异极大（本项目：宏观区块 417 行 vs 附录 200 行），
ratio 阈值会在长区块上迟迟不够、在短区块上又抢焦。改用**「触发线穿过区间」**：谁离视口顶的触发线最近就是谁。

```js
/* 取 offsetTop <= y + TOP_OFFSET 里 offsetTop 最大的那个 */
for (...) if (s.offsetTop - TOP_OFFSET <= y && s.offsetTop > best) { best = ...; active = id; }
/* 兜底：滚到页底时最后一章可能永远够不到触发线 */
if (!active && (innerHeight + y) >= docEl.scrollHeight - 4) active = LAST_ID;
```

**两级目录互斥**：宽屏用左侧固定目录，窄屏用右下角 `details` 折叠目录，中间档**两者都不显示**（留白更干净）。
不要同屏出现两个导航。用互不重叠的 media query 切换 `display`。

**点击要立即高亮，不等滚动结束**（否则有半秒"按了没反应"的观感）；窄屏点完顺便收起折叠目录。

### 12.2 断言口径：探针自己的断言也会写反

写交互探针时，**"代码看起来错了"往往其实是断言错了**。本项目实测三处：

| 写错的断言 | 错在哪 | 正确口径 |
|---|---|---|
| 「五项**全部**是当前章」 | 要求所有章节同时高亮 | 「**恰好**目标章亮、其余都不亮」 |
| 点链接后又 `setY(0)` 再读状态 | 当场把点击结果覆盖掉 | **只点、不跟滚动**，测的就是「点击→立即高亮」 |
| 用滚动条位置断言"跳转成功" | 无头下 `scrollTo` 根本不生效 | 改断言**状态变化**（哪一项高亮），而不是物理位置 |

### 12.3 完全离线单文件打包

**目标**：断网、无 DNS、无代理的环境下双击即完整渲染。

**做法：内联库源码 + 保留原就绪契约。** 关键点是**不要改主脚本**——
本项目主脚本用 `window.__onD3Ready(cb)` 注册渲染入口，内联后补一个**同签名**实现即可：

```python
# 把 <script src="CDN"> 加载器整段替换为：
#   1) <script>…d3.min.js 源码…</script>
#   2) <script>(function(){
#        var ok = (typeof d3 !== 'undefined');
#        window.__d3Loaded = ok;
#        window.__onD3Ready = function(fn){ fn(ok); };   // 同签名
#      })();</script>
```
**改动面越小，回归风险越低** —— 主脚本一行不动。

**三个必查细节**：
1. **内联前校验库源码不含 `</script`**（否则会提前闭合内联块）→ `if '</script' in src.lower(): sys.exit(...)`
2. **删掉 `preconnect` / `dns-prefetch` 提示** —— 纯离线文件不该有任何握手尝试
3. **定位替换片段时先做"像不像加载器"的自检**（断言片段里确实含 CDN 域名），避免误删无关代码

**校验器别用"裸字符串不存在"当判据。** 内联后文件里必然还留着域名文本
（库首行的版权注释 `// https://d3js.org v7.9.0 …`、错误兜底文案里的域名）。
这些都是**纯文本，不产生网络请求**。正确判据是**抹掉注释与字符串后再搜**：

```python
s = re.sub(r'<!--.*?-->', '', h, flags=re.S)      # HTML 注释
s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)        # JS 块注释
s = re.sub(r'//[^\n]*', '', s)                     # JS 行注释
s = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', s)        # 双引号串
s = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", s)        # 单引号串
leaked = [u for u in re.findall(r'https?://[^\s"\'<>)]+', s) if 'cdn-host' in u]
assert not leaked, '远程域名仅存在于注释/字符串中，可执行引用 0 处'
```
再补一条硬校验：`assert not re.search(r'\b(?:src|href)\s*=\s*["\']https?:', h)`。

**"离线可用"的机器证明：断网对照实验。** 只证明"离线版能跑"是不够的——
还要证明**测试环境确实断了网**，否则"能跑"可能只是缓存命中。做法：

```python
OFFLINE_ARGS = [
    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost',
    '--proxy-server=http://127.0.0.1:9',        # 必定拒绝连接的端口
    '--disable-background-networking',
]
# A. CDN 依赖版 → 预期：图表区出现 fallback、完整 SVG 数 = 0   （证明断网生效）
# B. 内联离线版 → 预期：fallback = 0、SVG 数 = 全部容器数        （证明离线能力来自内联）
```

⚠️ **数 fallback 时要先剥掉 `<script>` 块**：页面 JS 源码里有一句
`const msg = '<div class="fallback">…'`，`--dump-dom` 会原样带上这段字符串，
朴素 `html.count('class="fallback"')` 会把它也算进去（误报 1 处）。

### 12.4 双形态交付

保留两份文件，各有用处：
- `xxx.html` —— CDN 依赖版（体积小，开发/联调用）
- `xxx.offline.html` —— 内联离线版（体积大 ~2.3×，交付/离线演示用）

用同一个构建脚本产出离线版，**不要手工维护两份**。

---

## 十二、交付前检查清单

- [ ] D3 走异步加载器，主源超时能切镜像，双源全挂时有错误卡片
- [ ] 入场动画有 `setTimeout` 兜底，且兜底里先 `interrupt()` 再写终态
- [ ] `prefers-reduced-motion` 时直接落终态
- [ ] resize 重绘不重播动画（`isIntro` 标记）
- [ ] `ResizeObserver` 有 rAF 合并 + 宽度未变则跳过（防自触发死循环）
- [ ] **所有 `d3.pointer(event, X)` 的第二个参数是 DOM 节点（`.node()`），不是 d3 selection**
- [ ] **交互命中做了逐项断言**（每个刻度/数据点各点一遍，断言命中的就是它自己），三档宽度全绿
- [ ] **Tooltip 翻边后有 `Math.max(8, …)` 兜底**，460 宽度下所有分支 `left >= 0 && right <= innerWidth`
- [ ] 无头验证：`--screenshot` 与 `--dump-dom` **分两次**调用；截图用**绝对路径** + `--force-device-scale-factor=1`
- [ ] 面积图的 y0/y1 做了值域 clamp，且 `stroke: none`
- [ ] 数据点/标注框在 460 / 900 / 1440 三档宽度下都完整可见
- [ ] 图表数值与数据源逐值核对（脚本比对，不靠肉眼）
- [ ] tooltip 的每个条件分支都被验证过（含警示色分支）
- [ ] 无头环境 `--dump-dom` 检查：无 fallback 卡片、占位已移除、SVG 元素数正确
- [ ] **分面图元素计数**：面板数 / 每格路径数 / 点分数 / 参考线数 = 期望值（数值从数据源算，不写死）
- [ ] **`.data(大数组)` 在多组 selection 上只出现 1 次**（绑面板那一次），否则就是数据广播
- [ ] **`d3.pointer` 第二参数不是"带 x/y 的定位元素自指"**；用 `svg.node()` + 手工减面板偏移
- [ ] **最右列那一格**做 21 点横扫：单调不减，左端=首刻度、右端=末刻度、`x(目标)` 处命中目标
- [ ] **注解几何三类全查**：`<text>`×`<text>`、`<text>`×数据点、**`<text>`×线段** 重叠数均为 0
- [ ] **每一张子图各自跑一遍**注解碰撞断言（主图过了 ≠ 副图过了）
- [ ] **文字宽度估算按 CJK 全角算**（`len(t)*fs*0.56` 会漏报一半）
- [ ] **改完 HTML 先 `rm -f <workdir>/dom_*.html`** 再跑校验，避免读到缓存状态
- [ ] **密集点簇的标签**：确认是"整簇竖排 + 引线"，不是硬用通用避让（零空间处必失败）
- [ ] **响应式分支判据用实际可用宽度**（`iw` / 剩余空间），不要用外层容器宽度
- [ ] 自动检测全绿后，**抽 2–3 处放大截图人工确认**（框不相交 ≠ 标注贴对了对象 ≠ 没被粗线盖住）

**多区块长页 / 离线交付（第十二节）**

- [ ] 滚动监听 `passive:true` + 回调只写标记 + 测量推迟到 rAF（一帧最多算一次）
- [ ] scroll-spy 用「触发线穿过区间」，**不用** IO ratio；有"滚到底部"兜底
- [ ] 导航用 `position:fixed`（长页有 overflow 容器时 `sticky` 不可靠）
- [ ] 目录两形态**互斥**（宽屏侧栏 / 窄屏角落折叠 / 中间档都不显示），不重叠断点
- [ ] 点击目录**立即高亮**，不等滚动结束
- [ ] **交互探针的断言口径自查**："恰好一个高亮"而不是"全部高亮"；点击后不要再覆盖状态；用状态而非物理滚动位置断言
- [ ] **无头驱动先怀疑环境**：`scrollTo` 不生效、**rAF 在 `--virtual-time-budget` 耗尽前不触发** → 探针内做桩 + 截图另走一路
- [ ] 离线版：内联库源码（内联前查 `</script`）+ 保留原 `__onD3Ready` 同签名契约 + 删 `preconnect`
- [ ] 离线校验判据**抹掉注释/字符串后再搜域名**，不用"裸字符串不存在"
- [ ] **断网对照实验**：CDN 版必须失败、离线版必须全成——两条都成立才算证明"离线可用"
- [ ] 数 fallback 时**先剥 `<script>` 块**（否则把 JS 源码里的字符串算进去）
- [ ] **跨阶段回归时先审断言**：一条 FAIL 先分清「代码错了」还是「期望值过期了」，改完在注释里写清为什么变

