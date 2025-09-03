# Rubber Band Tool - Quick Reference

## 🚀 Launch Options

```bash
# Enable rubber band mode
./gui/run_gui.sh --rubber-band-mode

# Show help
./gui/run_gui.sh --help
```

## ⌨️ Keyboard Controls

| Key Combination | Action |
|----------------|--------|
| `ESC` | Toggle rubber band tool on/off |
| `Ctrl + Click + Drag` | Create selection rectangle (when tool is active) |
| `Right-click` | Cancel current selection |

## 🎯 Usage Workflow

1. **Launch**: `./gui/run_gui.sh --rubber-band-mode`
2. **Activate**: Press `ESC` to turn on rubber band selection
3. **Navigate**: Go to the GUI area you want to analyze
4. **Select**: Hold `Ctrl` and drag to select region
5. **Edit Prompt**: Modify the pre-filled AI prompt
6. **Save**: Click "Save to File" to generate outputs
7. **Toggle**: Press `ESC` to disable/enable tool as needed

## 📁 Output Files

Files saved to: `/tmp/emclarity_gui_prompts/`

- `gui_prompt_YYYYMMDD_HHMMSS.json` - Machine-readable format
- `gui_prompt_YYYYMMDD_HHMMSS.txt` - Human-readable format

## 🔧 Features

- ✅ Visual selection overlay
- ✅ Precise coordinate capture
- ✅ AI-ready prompt generation
- ✅ Non-destructive operation
- ✅ Keyboard shortcuts for efficiency
- ✅ Menu integration as fallback
- ✅ Comprehensive GUI context in prompts

## 🆘 Troubleshooting

**Tool not working?**
- Ensure you launched with `--rubber-band-mode` flag
- Check console for error messages
- Try toggling with F15 key

**Selections not registering?**
- Hold `Ctrl` while clicking and dragging
- Make sure selection is large enough (>10px)
- Check if overlay is visible

**ESC not working?**
- Only works when launched with `--rubber-band-mode`
- Alternative: Use View → Toggle Rubber Band Mode menu

## 💡 Pro Tips

- Use multiple selections for complex layouts
- Edit the prompt template for specific needs
- Combine with screenshots for better AI context
- Files are timestamped for easy organization
- Tool works alongside normal GUI operation
