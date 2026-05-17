# code-style

本文件定义项目中的代码风格补充规则，用于约束实现细节，避免重复出现同类问题。

## 导入规则（强制）

- 禁止使用“可选依赖兜底导入”模式：
    - 禁止 `try: import ... except ImportError/Exception: ...`
    - 禁止 `# type: ignore[import-not-found]` 配合降级逻辑
- 所有依赖必须直接导入：
    - 使用 `from xxx import yyy` 或 `import xxx`
    - 缺包时允许在启动或导入阶段直接报错，不做静默降级
- 禁止函数/方法/条件分支中的局部导入：
    - 禁止在函数体内写 `import` / `from ... import ...`
    - 统一在文件顶部导入依赖

## 原则

- 依赖问题应尽早暴露（fail fast），不要在运行时悄悄切换到弱化逻辑。
- 不为“可能缺包”的场景增加兼容分支。
- 如果确实需要新增依赖，应该更新依赖清单并让环境安装依赖，而不是写兜底代码。

## 代码评审检查项

- 新增或修改代码时，检查是否出现以下反模式：
    - `try` + `import` + `except ImportError/Exception`
    - 导入失败后将符号赋值为 `None` 再分支处理
    - 使用 `type: ignore[import-not-found]` 掩盖缺依赖问题
    - 在函数体/分支内做局部导入

违反以上规则的代码应直接修改为“直接导入”。

## 提交时自动检查

- 仓库提供了提交钩子：`.githooks/pre-commit`
- 该钩子会检查暂存区中的 `*.py` 文件，发现以下模式会阻止提交：
    - `try:` 块内出现 `import`
    - 对应 `except ImportError` 或 `except Exception`
    - 函数体（或任意缩进代码块）内出现 `import` / `from ... import ...`

首次在本地启用：

```powershell
git config core.hooksPath .githooks
```
