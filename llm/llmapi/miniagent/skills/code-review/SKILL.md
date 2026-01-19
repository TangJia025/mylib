---
name: code-review
description: 进行全面的代码审查，涵盖安全、性能与可维护性分析。适用于用户要求审查代码、排查缺陷或审计代码库的场景。
---

# 代码审查技能

你现在具备进行全面代码审查的专业能力。请遵循以下结构化方法：

## 审查清单

### 1. 安全（关键）

检查项：
- [ ] **注入漏洞**：SQL、命令、XSS、模板注入
- [ ] **认证问题**：硬编码凭据、弱认证
- [ ] **授权缺陷**：缺少访问控制、IDOR
- [ ] **数据泄露**：日志/错误信息暴露敏感数据
- [ ] **密码学**：弱算法、不当密钥管理
- [ ] **依赖项**：已知漏洞（使用 `npm audit`、`pip-audit` 等检查）

```bash
# 快速安全扫描
npm audit                    # Node.js
pip-audit                    # Python
cargo audit                  # Rust
grep -r "password\|secret\|api_key" --include="*.py" --include="*.js"
```

### 2. 正确性

检查项：
- [ ] **逻辑错误**：Off-by-one、空值处理、边界情况
- [ ] **竞态条件**：并发访问缺少同步
- [ ] **资源泄露**：文件/连接未关闭、内存泄露
- [ ] **错误处理**：吞异常、遗漏错误路径
- [ ] **类型安全**：隐式转换、any 类型滥用

### 3. 性能

检查项：
- [ ] **N+1 查询**：循环中发起数据库调用
- [ ] **内存问题**：大分配、引用保留导致无法释放
- [ ] **阻塞操作**：异步代码里使用同步 I/O
- [ ] **低效算法**：可以 O(n) 却写成 O(n^2)
- [ ] **缺少缓存**：重复做昂贵计算

### 4. 可维护性

检查项：
- [ ] **命名**：清晰、一致、可读
- [ ] **复杂度**：函数 > 50 行、嵌套层级 > 3
- [ ] **重复**：复制粘贴的代码块
- [ ] **死代码**：未使用的导入、不可达分支
- [ ] **注释**：过期、冗余，或该有却缺失

### 5. 测试

检查项：
- [ ] **覆盖率**：关键路径是否覆盖
- [ ] **边界用例**：空值、空集合、边界值
- [ ] **Mock**：外部依赖是否隔离
- [ ] **断言**：是否有意义、足够具体

## 审查输出格式

```markdown
## 代码审查：[文件/组件名]

### 概要
[1-2 句概述]

### 严重问题
1. **[问题]**（第 X 行）：[描述]
   - 影响：[可能的风险/后果]
   - 修复：[建议的解决方案]

### 改进建议
1. **[建议]**（第 X 行）：[描述]

### 正向反馈
- [做得好的地方]

### 结论
[ ] 可以合并
[ ] 需要小改
[ ] 需要大改
```

## 常见风险模式

### Python
```python
# 不推荐：SQL 注入
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
# 推荐：
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))

# 不推荐：命令注入
os.system(f"ls {user_input}")
# 推荐：
subprocess.run(["ls", user_input], check=True)

# 不推荐：可变默认参数
def append(item, lst=[]):  # Bug：可变默认参数会在多次调用间共享
# 推荐：
def append(item, lst=None):
    lst = lst or []
```

### JavaScript/TypeScript
```javascript
// 不推荐：原型污染
Object.assign(target, userInput)
// 推荐：
Object.assign(target, sanitize(userInput))

// 不推荐：使用 eval
eval(userCode)
// 推荐：不要对用户输入使用 eval

// 不推荐：回调地狱
getData(x => process(x, y => save(y, z => done(z))))
// 推荐：
const data = await getData();
const processed = await process(data);
await save(processed);
```

## 审查命令

```bash
# 查看最近变更
git diff HEAD~5 --stat
git log --oneline -10

# 查找潜在问题
grep -rn "TODO\|FIXME\|HACK\|XXX" .
grep -rn "password\|secret\|token" . --include="*.py"

# 检查复杂度（Python）
pip install radon && radon cc . -a

# 检查依赖
npm outdated  # Node
pip list --outdated  # Python
```

## 审查流程

1. **理解上下文**：阅读 PR 描述、关联的 Issue
2. **运行代码**：构建、测试，尽可能本地跑起来
3. **自顶向下阅读**：从主要入口开始
4. **检查测试**：变更是否有测试？测试是否通过？
5. **安全扫描**：运行自动化工具
6. **人工审查**：使用上面的清单逐项检查
7. **撰写反馈**：具体明确、给出修复建议、保持友好
