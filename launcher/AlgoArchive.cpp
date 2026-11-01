#include <windows.h>
#include <shellapi.h>

#include <string>
#include <vector>

namespace {

std::wstring ExecutableDirectory() {
    std::vector<wchar_t> buffer(1024);
    for (;;) {
        const DWORD length = GetModuleFileNameW(
            nullptr,
            buffer.data(),
            static_cast<DWORD>(buffer.size())
        );
        if (length == 0) {
            return {};
        }
        if (length < buffer.size() - 1) {
            std::wstring path(buffer.data(), length);
            const std::size_t separator = path.find_last_of(L"\\/");
            return separator == std::wstring::npos
                ? std::wstring()
                : path.substr(0, separator);
        }
        buffer.resize(buffer.size() * 2);
    }
}

std::wstring QuoteArgument(const std::wstring& argument) {
    if (argument.empty()) {
        return L"\"\"";
    }
    if (argument.find_first_of(L" \t\n\v\"") == std::wstring::npos) {
        return argument;
    }

    std::wstring quoted = L"\"";
    std::size_t backslashes = 0;
    for (wchar_t character : argument) {
        if (character == L'\\') {
            ++backslashes;
            continue;
        }
        if (character == L'"') {
            quoted.append(backslashes * 2 + 1, L'\\');
            quoted.push_back(L'"');
            backslashes = 0;
            continue;
        }
        quoted.append(backslashes, L'\\');
        backslashes = 0;
        quoted.push_back(character);
    }
    quoted.append(backslashes * 2, L'\\');
    quoted.push_back(L'"');
    return quoted;
}

std::wstring LauncherArguments() {
    int argument_count = 0;
    LPWSTR* arguments = CommandLineToArgvW(
        GetCommandLineW(),
        &argument_count
    );
    if (arguments == nullptr) {
        return {};
    }

    std::wstring result;
    for (int index = 1; index < argument_count; ++index) {
        if (!result.empty()) {
            result.push_back(L' ');
        }
        result += QuoteArgument(arguments[index]);
    }
    LocalFree(arguments);
    return result;
}

void ShowFailure(const wchar_t* detail) {
    std::wstring message =
        L"AlgoArchive cannot start from this directory.\n\n";
    message += detail;
    MessageBoxW(
        nullptr,
        message.c_str(),
        L"AlgoArchive",
        MB_OK | MB_ICONERROR | MB_SETFOREGROUND
    );
}

}  // namespace

int WINAPI wWinMain(
    HINSTANCE,
    HINSTANCE,
    PWSTR,
    int
) {
    const std::wstring directory = ExecutableDirectory();
    if (directory.empty()) {
        ShowFailure(L"Unable to determine the program directory.");
        return 1;
    }

    const std::wstring start_script = directory + L"\\start.bat";
    const DWORD attributes = GetFileAttributesW(start_script.c_str());
    if (
        attributes == INVALID_FILE_ATTRIBUTES ||
        (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0
    ) {
        ShowFailure(L"start.bat is missing. Extract or install the complete package.");
        return 1;
    }

    const std::wstring arguments = LauncherArguments();
    SetCurrentDirectoryW(directory.c_str());
    const HINSTANCE result = ShellExecuteW(
        nullptr,
        L"open",
        start_script.c_str(),
        arguments.empty() ? nullptr : arguments.c_str(),
        directory.c_str(),
        SW_SHOWNORMAL
    );
    if (reinterpret_cast<INT_PTR>(result) <= 32) {
        ShowFailure(L"start.bat could not be opened by Windows.");
        return 1;
    }
    return 0;
}
