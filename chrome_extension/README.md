# 视频下载助手 Chrome插件

## 功能介绍

这是一个Chrome浏览器扩展插件，可以在YouTube、Twitter/X、Bilibili等视频网站上添加下载按钮，将视频任务添加到闲时下载队列中，配合现有的PyQt GUI应用实现自动化视频下载和处理。

## 支持的网站

- **YouTube** - youtube.com
- **Twitter/X** - twitter.com, x.com  
- **Bilibili** - bilibili.com

## 主要功能

1. **页面按钮注入** - 在支持的网站上自动添加"添加到下载队列"按钮
2. **队列管理** - 通过popup界面查看和管理下载队列
3. **设置配置** - 配置闲时下载时间和其他参数
4. **队列导出** - 将队列导出为JSON文件，供GUI应用使用

## 安装方法

### 开发者模式安装

1. 打开Chrome浏览器，进入 `chrome://extensions/`
2. 开启右上角的"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择 `chrome_extension` 文件夹
5. 插件将出现在扩展程序列表中

## 使用方法

### 1. 添加视频到队列

1. 访问支持的视频网站（YouTube、Twitter/X、Bilibili）
2. 在视频页面上找到橙色的"添加到下载队列"按钮
3. 点击按钮，视频将被添加到队列中
4. 按钮会显示"已添加到队列"的成功状态

### 2. 管理下载队列

1. 点击浏览器工具栏中的插件图标
2. 在弹出的popup窗口中查看当前队列
3. 可以执行以下操作：
   - **导出队列** - 将队列保存为JSON文件
   - **清空队列** - 删除所有队列中的任务
   - **刷新** - 重新加载队列状态

### 3. 配置设置

1. 在popup窗口中切换到"设置"选项卡
2. 设置闲时下载时间（例如：23:00 - 07:00）
3. 可选：设置GUI应用路径（用于高级同步功能）
4. 点击"保存设置"

### 4. 与GUI应用集成

插件会将队列数据导出为JSON文件，格式与现有GUI应用的 `idle_queue.json` 兼容：

```json
{
  "tasks": [
    {
      "type": "youtube",
      "params": {
        "youtube_url": "https://www.youtube.com/watch?v=...",
        "download_video": true,
        "generate_subtitles": true,
        // 其他参数...
      },
      "title": "视频: 视频标题",
      "addedTime": "2025-09-10T12:00:00.000Z",
      "platform": "youtube"
    }
  ],
  "idle_start_time": "23:00",
  "idle_end_time": "07:00"
}
```

## 集成步骤

### 方法1：手动导出导入

1. 在插件popup中点击"导出队列"
2. 下载生成的JSON文件
3. 将文件内容复制到GUI应用目录下的 `idle_queue.json` 文件中
4. GUI应用会自动读取并处理队列中的任务

### 方法2：文件监听（推荐）

为了实现更好的自动化集成，可以修改GUI应用来监听特定目录：

1. 设置Chrome下载目录为GUI应用可监听的位置
2. 插件导出文件时使用固定的文件名格式
3. GUI应用监听该目录，自动导入新的队列文件

## 文件结构

```
chrome_extension/
├── manifest.json              # 插件配置文件
├── background.js             # 后台服务脚本
├── content-scripts/          # 内容脚本目录
│   ├── youtube.js           # YouTube页面脚本
│   ├── twitter.js           # Twitter页面脚本
│   ├── bilibili.js          # Bilibili页面脚本
│   └── styles.css           # 通用样式
├── popup/                   # 弹窗界面
│   ├── popup.html
│   ├── popup.js
│   └── popup.css
├── icons/                   # 图标文件
│   ├── icon16.png
│   ├── icon32.png
│   ├── icon48.png
│   └── icon128.png
└── README.md               # 说明文档
```

## 技术特性

- **Manifest V3** - 使用最新的Chrome插件标准
- **跨站点支持** - 支持多个视频平台的统一接口
- **响应式UI** - 适配不同屏幕尺寸的popup界面
- **数据持久化** - 使用Chrome存储API保存队列和设置
- **错误处理** - 完善的错误提示和状态反馈

## 开发说明

如需修改或扩展插件功能：

1. **添加新网站支持**：
   - 在 `manifest.json` 中添加新的 `host_permissions` 和 `content_scripts`
   - 创建对应的内容脚本文件
   - 实现页面检测和按钮注入逻辑

2. **修改UI样式**：
   - 编辑 `popup/popup.css` 文件
   - 修改 `content-scripts/styles.css` 中的按钮样式

3. **扩展通信机制**：
   - 修改 `background.js` 中的消息处理逻辑
   - 实现更高级的与本地应用通信方式

## 注意事项

1. **权限要求** - 插件需要访问指定网站的权限
2. **网站更新** - 网站页面结构变化可能影响按钮注入
3. **浏览器兼容性** - 基于Manifest V3，需要较新版本的Chrome
4. **数据安全** - 队列数据存储在本地，不会上传到服务器

## 故障排除

### 按钮不显示
- 检查是否在支持的网站上
- 确认插件已启用
- 刷新页面重试

### 队列导出失败
- 检查浏览器下载权限
- 确认有队列数据
- 查看浏览器控制台错误信息

### 与GUI应用同步问题
- 检查导出的JSON文件格式
- 确认GUI应用的 `idle_queue.json` 文件权限
- 验证文件路径是否正确