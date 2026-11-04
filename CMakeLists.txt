cmake_minimum_required(VERSION 3.25)
project(runbox VERSION 0.1.1 LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Export compile commands for clang-tidy / IDE integration
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Strict warning flags
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(
        -Wall
        -Wextra
        -Wpedantic
        -Wconversion
        -Wsign-conversion
        -Wshadow
        -Wnon-virtual-dtor
        -Wold-style-cast
        -Wcast-align
        -Wunused
        -Woverloaded-virtual
        -Wformat=2
    )
endif()

# Find dependencies
find_package(PkgConfig REQUIRED)
pkg_check_modules(SECCOMP REQUIRED libseccomp)
find_package(Threads REQUIRED)

# Core library sources
set(RUNBOX_CORE_SOURCES
    core/process/process.cpp
    core/namespaces/namespaces.cpp
    core/cgroups/cgroup_manager.cpp
    core/seccomp/seccomp_rules.cpp
    core/filesystem/filesystem_isolation.cpp
    core/security/privileges.cpp
    core/monitoring/monitor.cpp
    core/supervisor/supervisor.cpp
    core/supervisor/config.cpp
)

add_library(runbox_core STATIC ${RUNBOX_CORE_SOURCES})
target_include_directories(runbox_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${SECCOMP_INCLUDE_DIRS}
)
target_link_libraries(runbox_core PUBLIC
    ${SECCOMP_LIBRARIES}
    Threads::Threads
)

# Code coverage scoped to runbox_core only (prevents instrumenting third-party gtest)
option(ENABLE_COVERAGE "Enable Gcov code coverage instrumentation" OFF)
if(ENABLE_COVERAGE AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    message(STATUS "Enabling Code Coverage instrumentation for runbox_core (--coverage)")
    target_compile_options(runbox_core PUBLIC --coverage -O0 -g)
    target_compile_definitions(runbox_core PUBLIC RUNBOX_ENABLE_COVERAGE)
    target_link_options(runbox_core PUBLIC --coverage)
endif()

# Supervisor executable
add_executable(runbox-supervisor core/supervisor/main.cpp)
target_link_libraries(runbox-supervisor PRIVATE runbox_core)

# Tests
option(BUILD_TESTS "Build GoogleTest test suite" ON)
if(BUILD_TESTS)
    include(FetchContent)
    FetchContent_Declare(
        googletest
        URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.tar.gz
        DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    )
    # Prevent overriding parent project compiler/linker settings on Windows/Linux
    set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
    set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(googletest)

    set(TEST_SOURCES
        tests/unit/test_process.cpp
        tests/unit/test_config.cpp
        tests/unit/test_cgroups.cpp
        tests/unit/test_namespaces.cpp
        tests/unit/test_seccomp.cpp
        tests/unit/test_filesystem.cpp
        tests/unit/test_privileges.cpp
        tests/unit/test_monitor.cpp
        tests/integration/test_supervisor.cpp
        tests/security/test_sandbox_security.cpp
    )

    add_executable(runbox_tests ${TEST_SOURCES})
    target_link_libraries(runbox_tests PRIVATE runbox_core gtest_main)
    target_include_directories(runbox_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

    include(GoogleTest)
    gtest_discover_tests(runbox_tests)
endif()
