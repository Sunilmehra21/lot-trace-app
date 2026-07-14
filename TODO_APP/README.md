# To-Do List Application

A modern, feature-rich to-do list application with local storage functionality. Built with vanilla JavaScript, HTML, and CSS.

## ✨ Features

### Core Functionality
- ✅ **Add Tasks** - Create new tasks with a single click or Enter key
- ✅ **Complete Tasks** - Check off completed tasks with visual feedback
- ✅ **Delete Tasks** - Remove individual tasks
- ✅ **Priority Levels** - Set priority (High, Medium, Low) for each task
- ✅ **Local Storage** - All tasks are automatically saved to browser's local storage
- ✅ **Filter Tasks** - View All, Active, Completed, or High Priority tasks
- ✅ **Statistics** - Real-time stats showing Total, Completed, and Pending tasks

### User Experience
- 🎨 **Beautiful UI** - Modern gradient design with smooth animations
- 📱 **Responsive Design** - Works seamlessly on desktop, tablet, and mobile
- 🔔 **Notifications** - Toast notifications for user actions
- ⌨️ **Keyboard Support** - Add tasks with Enter key
- 🎯 **Input Validation** - Prevents empty or too-long tasks
- 🔒 **XSS Protection** - Escapes HTML to prevent security issues

### Data Management
- 💾 **Auto-Save** - Tasks are automatically saved to local storage
- 🔄 **Persistent Data** - Tasks survive browser refresh and session restart
- 📊 **Clear Options** - Clear completed tasks or all tasks at once
- ⚠️ **Confirmation Dialogs** - Prevents accidental deletion

## 🚀 Usage

### Getting Started

1. **Open the application** - Simply open `index.html` in your web browser
2. **Add a task** - Type in the input field and click "+" or press Enter
3. **Select priority** - Choose priority level before adding task
4. **Manage tasks** - Check off, delete, or filter tasks as needed

### Adding Tasks
- Type your task in the input field
- Select priority from the dropdown (Low, Medium, High)
- Click the "+" button or press Enter
- Task is instantly saved to local storage

### Filtering Tasks
- **All** - Shows all tasks
- **Active** - Shows only incomplete tasks
- **Completed** - Shows only completed tasks
- **High Priority** - Shows only high priority tasks

### Managing Tasks
- **Complete Task** - Click the checkbox to mark as complete
- **Delete Task** - Click the Delete button to remove a task
- **Clear Completed** - Remove all completed tasks at once
- **Clear All** - Remove all tasks (with confirmation)

## 💾 Local Storage

All tasks are automatically saved to the browser's local storage under the key `todoAppTasks`. The data persists across:
- Browser refreshes
- Browser sessions
- Multiple tabs/windows (same browser)

### Storage Format
```json
[
  {
    "id": 1720951234567,
    "text": "Example task",
    "completed": false,
    "priority": "high",
    "createdAt": "2024-07-14T09:00:00.000Z"
  }
]
```

### Clearing Storage
To clear all tasks and reset the app:
1. Click "Clear All" button and confirm
2. Or open Developer Tools (F12) → Application → Local Storage → Delete `todoAppTasks`

## 🛠️ Technical Details

### Architecture
- **Object-Oriented** - Implemented as a `TodoApp` class for easy maintenance
- **State Management** - Simple state management with `todos` array
- **Event Handling** - Delegated event listeners for efficiency
- **DOM Manipulation** - Direct DOM operations for better performance

### Files
- `index.html` - Semantic HTML structure
- `styles.css` - Beautiful gradient design with animations
- `app.js` - Class-based application logic

### Key Methods
- `addTodo()` - Creates and stores new task
- `toggleTodo(id)` - Marks task as complete/incomplete
- `deleteTodo(id)` - Removes a task
- `setFilter(filter)` - Changes current filter
- `clearCompleted()` - Removes all completed tasks
- `clearAll()` - Removes all tasks
- `render()` - Re-renders the UI based on current state
- `saveTodos()` - Saves todos to local storage
- `loadTodos()` - Loads todos from local storage

## 🔐 Security Features

- **HTML Escaping** - Prevents XSS attacks by escaping HTML characters
- **Input Validation** - Validates task length and content
- **Confirmation Dialogs** - Prevents accidental data loss

## 📱 Browser Compatibility

- ✅ Chrome/Edge 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)

**Note**: Requires Local Storage support (available in all modern browsers)

## 🎨 Customization

### Colors
Edit the gradient colors in `styles.css`:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### Animation Speed
Modify animation duration in `styles.css`:
```css
animation: slideUp 0.5s ease-out;
```

### Storage Key
Change the storage key in `app.js`:
```javascript
this.storageKey = 'yourCustomKey';
```

## 📦 Deployment

### As Static Website
1. Upload all three files to your web server
2. Ensure all files are in the same directory
3. Access via your domain

### GitHub Pages
1. Create a new repository
2. Add all files to the repository
3. Enable GitHub Pages in repository settings
4. Access via `yourusername.github.io/repo-name`

## 🐛 Troubleshooting

### Tasks Not Saving
- Check if Local Storage is enabled in browser
- Check browser console for errors (F12)
- Verify storage quota isn't exceeded

### Tasks Disappearing
- Check if private/incognito mode is enabled (disables Local Storage)
- Verify browser Local Storage is not being cleared on exit
- Check if storage quota was exceeded

### Performance Issues
- If 1000+ tasks exist, consider exporting and clearing old tasks
- Local Storage has ~5-10MB limit depending on browser

## 📄 License

Free to use for personal and commercial projects.

## 🎯 Future Enhancements

- [ ] Task categories/projects
- [ ] Due dates and reminders
- [ ] Task notes/descriptions
- [ ] Dark mode
- [ ] Export/Import tasks
- [ ] Cloud sync
- [ ] Recurring tasks
- [ ] Task search
- [ ] Undo/Redo functionality
- [ ] Time tracking

## 💡 Tips & Tricks

1. **Quick Add** - Use Enter key for faster task creation
2. **Bulk Actions** - Use "Clear Completed" to manage large task lists
3. **Filtering** - Use filters to focus on specific task types
4. **Priority Management** - Use High Priority filter to focus on important tasks
5. **Backup** - Periodically export your tasks to a text file for backup

---

**Enjoy your new To-Do List App! 🎉**
