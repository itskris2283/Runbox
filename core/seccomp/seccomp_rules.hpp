#pragma once

#include <string>

namespace runbox::seccomp {

enum class SeccompProfile {
    Minimal,
    PythonExecution,
    CppCompilation,
    CppExecution
};

class SeccompFilter {
public:
    explicit SeccompFilter(SeccompProfile profile = SeccompProfile::Minimal);
    ~SeccompFilter() = default;

    // Installs PR_SET_NO_NEW_PRIVS and loads the BPF filter into the current process
    bool install();

    [[nodiscard]] SeccompProfile get_profile() const noexcept { return profile_; }

private:
    SeccompProfile profile_;

    bool build_and_load_filter();
};

} // namespace runbox::seccomp
