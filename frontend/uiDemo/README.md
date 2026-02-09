# BabyCareUI 
## 项目结构

```
ios/
├── BabyCareUI.xcodeproj/       # Xcode 项目文件
└── BabyCareUI/                 # 源代码目录
    ├── BabyCareUIApp.swift     # 应用入口
    ├── ContentView.swift       # 主界面（TabView）
    ├── Theme.swift             # 主题和样式定义
    ├── Views/                  # 视图组件
    │   ├── HomeLiveStatusView.swift      # 首页实时状态
    │   ├── ActivityHistoryView.swift     # 活动历史
    │   └── AIInsightsView.swift          # AI 洞察
    └── Resources/              # 资源文件
        ├── Assets.xcassets     # 图片资源
        └── LaunchScreen.storyboard  # 启动画面
```

## 启动项目

### 方法 1：使用 Xcode（推荐）

1. 打开 Xcode
2. 打开项目文件：
   ```bash
   open BabyCareUI.xcodeproj
   ```
3. 选择目标设备（iPhone 模拟器或真机）
4. 点击运行按钮（⌘R）或选择 Product > Run

### 方法 2：使用命令行

```bash
# 构建项目
xcodebuild -project BabyCareUI.xcodeproj -scheme BabyCareUI -configuration Debug

# 运行在模拟器
xcodebuild -project BabyCareUI.xcodeproj -scheme BabyCareUI -destination 'platform=iOS Simulator,name=iPhone 15' build
```

### 方法 3：快速启动模拟器

```bash
# 在 iOS 模拟器中构建并运行
open -a Simulator
xcodebuild -project BabyCareUI.xcodeproj \
  -scheme BabyCareUI \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  -configuration Debug \
  build
```

## 系统要求

- macOS 13.0 或更高版本
- Xcode 15.0 或更高版本
- iOS 15.0+ 部署目标
- Swift 5.9+


## 开发说明

### 添加新功能

1. 在 `Views/` 目录下创建新的视图文件
2. 在 `ContentView.swift` 中引用新视图
3. 如需自定义样式，在 `Theme.swift` 中添加

### 构建配置

- **Bundle ID**: `com.babycare.BabyCareUI`
- **部署目标**: iOS 15.0
- **设备**: iPhone 和 iPad 通用

## 许可证

MIT License

