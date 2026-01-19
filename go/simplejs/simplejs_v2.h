#pragma once

#include <string>
#include <vector>
#include <functional>
#include <cstdint>
#include <memory>
#include <stdexcept>

namespace simplejs {

// JavaScript value types
enum class Type : uint8_t {
    Object = 0,    // Object type
    Prop = 1,      // Property type
    String = 2,    // String type
    // Must be 0, 1, 2 for memory layout compatibility if we keep the same heap structure
    
    Undefined = 3,
    Null,
    Number,
    Boolean,
    Function,
    CodeRef,
    CFunc,
    Error,
    NaN
};

// Forward declaration
class Interpreter;

// Wrapper for JS value (NaN-boxed)
class Value {
public:
    using RawType = uint64_t;
    
    Value() : val_(0) {} // Default to invalid/zero? Or Undefined?
    explicit Value(RawType v) : val_(v) {}
    
    // Type checking
    bool isNumber() const;
    bool isString() const;
    bool isBoolean() const;
    bool isObject() const;
    bool isUndefined() const;
    bool isNull() const;
    bool isError() const;
    bool isCodeRef() const;
    
    // Conversion
    double toNumber() const;
    bool toBoolean() const;
    RawType raw() const { return val_; }

    static Value makeNumber(double d);
    static Value makeBoolean(bool b);
    static Value makeUndefined();
    static Value makeNull();
    // String and Object creation require Interpreter context for memory allocation
    
private:
    RawType val_;
    friend class Interpreter;
};

// C Function callback type
using NativeFunction = std::function<Value(Interpreter&, const std::vector<Value>&)>;

class Interpreter {
public:
    explicit Interpreter(size_t memory_size = 1024 * 16);
    ~Interpreter();

    // Prevent copying
    Interpreter(const Interpreter&) = delete;
    Interpreter& operator=(const Interpreter&) = delete;

    // Execute JS code
    Value eval(const std::string& code);
    
    // Global object access
    Value getGlobalObject();
    
    // Value creation helper
    Value createString(const std::string& s);
    Value createFunction(NativeFunction fn);
    Value createObject();
    Value createError(const std::string& msg);
    
    // Property access
    void setProperty(Value obj, const std::string& key, Value val);
    Value getProperty(Value obj, const std::string& key); // Basic get, might need more for prototype chain
    
    // Utils
    std::string toString(Value v);
    void dumpStats();
    
    // For internal use / testing
    void setMaxStackSize(size_t size);
    void setGCTrigger(size_t threshold_percent);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

class Error : public std::runtime_error {
public:
    explicit Error(const std::string& msg) : std::runtime_error(msg) {}
};

} // namespace simplejs
