CXX = g++
CXXFLAGS = -O2 -Wall -g -DJS_DUMP

.PHONY: test test_v2 clean help

test: simplejs.cc test.cc
	$(CXX) $(CXXFLAGS) -o test_runner simplejs.cc test.cc
	./test_runner

test_v2: simplejs_v2.cc test_v2.cc
	$(CXX) $(CXXFLAGS) -std=c++11 -o test_runner_v2 simplejs_v2.cc test_v2.cc
	./test_runner_v2

clean:
	rm -f test_runner test_runner_v2

help:
	@echo "SimpleJS Makefile"
	@echo "Targets:"
	@echo "  test    : Compile and run original tests"
	@echo "  test_v2 : Compile and run v2 tests (C++11 refactor)"
	@echo "  clean   : Remove build artifacts"
	@echo "  help    : Show this help message"
