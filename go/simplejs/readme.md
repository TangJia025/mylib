# SimpleJS (v3.0.0)

SimpleJS 是一个轻量级的 JavaScript 解释器，使用 C 语言编写（兼容 C++ 编译），旨在为嵌入式系统或资源受限环境提供基本的脚本能力。

核心代码仅包含两个文件：`simplejs.cc` 和 `simplejs.h`。

## 主要特性

*   **极简设计**: 无外部依赖，易于集成。
*   **内存高效**:
    *   使用 **NaN-boxing** 技术将所有值（数字、指针、布尔值等）打包在 64 位整数 (`jsval_t`) 中。
    *   **自带垃圾回收 (GC)**: 实现简单的标记-清除 (Mark-and-Sweep) 算法，自动管理内存。
    *   **自定义内存分配**: 所有的内存分配都在用户提供的单一连续缓冲区中进行，无 `malloc` 碎片问题。
*   **语言支持**:
    *   **变量**: `let`, `var`, `const` 声明。
    *   **类型**: Number (double), String, Boolean, Object, Function, Null, Undefined.
    *   **控制流**: `if`, `else`, `while`, `for`, `break`, `return`.
    *   **函数**: 支持 JS 定义的函数和 C 语言原生函数绑定。
    *   **对象**: 支持对象字面量 `{k:v}` 和属性访问 `obj.prop`。
    *   **运算**: 支持常见算术、位运算、逻辑和比较操作符。

## 快速开始

### 1. 编译与运行测试

项目提供了一个简单的 `Makefile`。

```bash
# 运行测试
make test

# 查看帮助
make help

# 清理
make clean
```

### 2. 代码示例

```c
#include "simplejs.h"
#include <stdio.h>

int main() {
    // 1. 分配一块内存给 JS 引擎使用
    char mem[1024 * 64]; // 64KB
    
    // 2. 创建 JS 实例
    struct js *js = js_create(mem, sizeof(mem));
    
    // 3. 执行 JavaScript 代码
    const char *code = "let x = 10; let y = 20; x * y;";
    jsval_t result = js_eval(js, code, 30); // 传入代码和长度
    
    // 4. 获取结果
    if (js_type(result) == JS_NUM) {
        printf("Result: %f\n", js_getnum(result)); // 输出 200.000000
    }
    
    // 5. 打印结果字符串
    const char *str = js_str(js, result);
    printf("String representation: %s\n", str);
    
    return 0;
}
```

## API 参考

所有公共 API 定义在 `simplejs.h` 中。

### 核心管理

*   `struct js *js_create(void *buf, size_t len)`: 初始化 JS 引擎。`buf` 是用于堆和栈的内存块。
*   `void js_setgct(struct js *js, size_t threshold)`: 设置垃圾回收触发阈值（字节数）。
*   `void js_setmaxcss(struct js *js, size_t size)`: 设置 C 栈最大使用深度限制。
*   `void js_stats(...)`: 获取内存使用统计信息。

### 执行与求值

*   `jsval_t js_eval(struct js *js, const char *code, size_t len)`: 解析并执行 JS 代码。
*   `jsval_t js_glob(struct js *js)`: 获取全局对象 (Global Object)。

### 值操作 (jsval_t)

SimpleJS 使用 `jsval_t` 类型表示所有 JS 值。

*   **类型检查**:
    *   `int js_type(jsval_t val)`: 返回值类型 (如 `JS_NUM`, `JS_STR`, `JS_OBJ` 等)。
    *   `bool js_truthy(struct js *js, jsval_t val)`: 判断值在布尔上下文是否为真。

*   **创建值 (C -> JS)**:
    *   `js_mknum(double)`: 创建数字。
    *   `js_mkstr(js, ptr, len)`: 创建字符串。
    *   `js_mkobj(js)`: 创建空对象。
    *   `js_mkfun(c_func_ptr)`: 创建 C 函数包装。
    *   `js_mktrue()`, `js_mkfalse()`, `js_mkundef()`, `js_mknull()`: 创建基础值。

*   **获取值 (JS -> C)**:
    *   `double js_getnum(jsval_t)`: 获取数字值。
    *   `int js_getbool(jsval_t)`: 获取布尔值 (0 或 1)。
    *   `char *js_getstr(js, val, &len)`: 获取字符串内容。

### C 函数绑定

你可以将 C 函数注册到 JS 环境中被调用。C 函数签名必须符合：
`jsval_t my_func(struct js *js, jsval_t *args, int nargs)`

示例：

```c
// 定义 C 函数
jsval_t c_add(struct js *js, jsval_t *args, int nargs) {
    if (nargs < 2) return js_mknum(0);
    double a = js_getnum(args[0]);
    double b = js_getnum(args[1]);
    return js_mknum(a + b);
}

// 注册到全局作用域
void register_funcs(struct js *js) {
    jsval_t global = js_glob(js);
    jsval_t func = js_mkfun(c_add);
    js_set(js, global, "add", func);
}
```

## 架构说明

SimpleJS 采用单遍解析（Single-pass parsing）和直接执行的架构，没有生成字节码或 AST 树，从而极大地降低了内存开销。

*   **Parser**: 递归下降解析器。
*   **Values**: 64-bit NaN-boxing。
*   **Memory**: 线性分配器 + 标记清除 GC。

## 许可证

MIT License
