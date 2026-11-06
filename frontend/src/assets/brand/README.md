# 品牌主标 · 原始素材（仅作构建源，不直接参与运行时）

本目录存放用户提供的原始大图，随前端代码一起版本管理。**不要直接 `import` 这里的 PNG**：
`logo.png` 单张 1.5MB，直接塞进首屏会明显拖慢加载。页面实际加载的是下面这些优化副本。

| 源图 | 体积 | 运行时产物 | 用途 | 产物体积 |
|---|---|---|---|---|
| `logo.png`（2048²） | 1.5 MB | `src/assets/images/logo-mark.png`（512²） | 首屏玻璃节点内主标 | 116 KB |
| `logosmall.png`（1024²） | 472 KB | `src/assets/images/logo-icon.png`（128²） | 顶栏品牌标 | 13.8 KB |
| `logosmall.png`（1024²） | 472 KB | `public/favicon.png`（64²） | 浏览器标签图标 | 4.9 KB |

生成方式：按 alpha 外接框裁成方形画布（四周留约 10% 透明边），LANCZOS 缩放到目标尺寸，
PNG `optimize=True` 保存。原图四周透明留白较多，直接等比缩放会让中间的 "A" 显得过小。

## Vite 的两条资产路径

- **`src/assets/**` 被组件 `import`** → Vite 处理、加内容 hash、输出到 `dist/assets/`。
  顶标（`layouts/AppHeader.vue`）与首屏节点（`views/home/index.vue`）走这条。
- **`public/**`** → 原样复制到 `dist/` 根，URL 固定。favicon 必须走这条，因为
  `frontend/index.html` 里写死了 `/favicon.png`，带 hash 反而引用不到。

本目录的源图没有被任何组件 import，因此**不会进入 dist**；只有上面三份优化副本会随构建发布。

`docs/assets/` 只是素材临时投放区，不参与构建，后续增删或替换都不影响站点。
