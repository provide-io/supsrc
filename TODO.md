# 🔼 Supsrc TODO List

## ✅ Completed
- [x] Fix watch command TUI to show actual repositories
- [x] Remove test repository from TUI on_mount  
- [x] Fix log formatting in TUI mode
- [x] Fix git repository reinitialization handling
- [x] Fix DataTable 'update_row' attribute error
- [x] Fix Index 'is_empty' attribute error
- [x] Run ruff format on supsrc codebase
- [x] Run ruff check --fix --unsafe-fixes
- [x] Run mypy type checking
- [x] Add emoji headers/footers to all files
- [x] **Suspend/pause controls in CLI** - Hit 's' to suspend or 'p' to pause during operations
- [x] **Hot reload for config changes** - Config automatically reloads on changes with 90s pause

## 🚨 High Priority - Core Functionality

### Configuration & Control
*(All items completed)*

### Server Architecture  
- [ ] **Design supsrc server based on pyvider-rpcplugin** - Core server architecture
- [ ] **Consider server architecture for datamodel/widgets/views** - Keep future server design in mind
- [ ] **Make server run programs like pytest** - Enable CLI to update/watch pytest output

## 🎯 Medium Priority - Enhanced Features

### Git Operations
- [ ] **Commit Cook (LLM Integration)** - Cook up intelligent commit messages from git diffs
- [ ] **Auto-save to different sessions** - Based on time period between last commit and save
- [ ] **Advanced tqdm integration** - Status spinner when pushing/pulling
- [ ] **Auto-freeze on conflict** - Push notification (macOS corner notification) when issues arise
- [ ] **Queue signed commits** - Support for queuing up signed commits

### Organization
- [ ] **Repository groups/tags** - Implement groups or tags (e.g., 'ofnote')

## 📋 Low Priority - Nice to Have

### Advanced Rules & Monitoring
- [ ] **Watch single file** - Copy/move to filename matching predefined pattern
- [ ] **Content-based rules** - Trigger actions based on file content changes
  - If these 3 files change, then tag it
  - Custom rule definitions

### Future Integrations
- [ ] **Generate env.sh via wrkenv action** - Future state integration with wrkenv
- [ ] **'Super supsrc supporter' feature** - Premium/advanced features

### Documentation
- [ ] **Add warranty disclaimer** - Legal/warranty information

## 🏗️ Architecture Notes

### Server Design (pyvider-rpcplugin based)
- gRPC-based communication
- Plugin architecture for extensibility
- Async operations throughout
- Clean separation between server and CLI

### Data Model Considerations
- Repository states as central entities
- Action queue management
- Event streaming for real-time updates
- Persistent state storage

### TUI Improvements
- Better error recovery
- Smooth updates without flicker
- Keyboard shortcut consistency
- Responsive layout adjustments

## 🔧 Technical Debt
- [ ] Complete mypy fixes (98 errors remaining)
- [ ] Run bandit security analysis
- [ ] Improve test coverage
- [ ] Better error messages and logging

---

*Last Updated: 2025-08-09*


# 🔼⚙️* let me hup/change/auto reload configs. i.e. i want a temporary 90s pause.
* allow suspend/status/etc in the CLI when waiting. - i.e. hit "s" to suspend. or possibly "p" to pause.
* make it a server that then will also run programs like pytest. then enable the cli to update/watch pytest.
* auto save to different "sessions" based on time period between last commit and save.
* advanced tqdm integration - i.e. status spinner when pushing/pulling.
* auto-freeze operation based on conflict. push notification that something is wrong (i.e. macos notification iun corner)
* repo groups - or tags? `ofnote`? ;)
* warranty. or lack there of.
* queuing up signed commits?
* watching a single file, then copying/moving to a filename that matches a predefined pattern.
* rules based on the content of the file that changed.
  - did these 3 files change? then tag it.
  - 
* `super supsrc supporter`


