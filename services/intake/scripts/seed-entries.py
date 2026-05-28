# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Script to seed the Intake service with diverse, realistic entry records.

Posts to the v2 Intake API. Creates three types of diverse tasks:
1. Conversational Support - Progressive 10-turn conversation with user feedback events
2. Tool Calling Examples - Single-turn tool calling scenarios with occasional user feedback
3. Query Rewriting - Complex question rewriting with user feedback and reviewer corrections

Examples:
    # Seed the local quickstart
    python -m scripts.seed-entries

    # Seed a deployed environment
    python -m scripts.seed-entries --api-url https://nemo.example.com

    # Seed a non-default workspace
    python -m scripts.seed-entries --workspace my-team

    # Delete all existing entries in the target workspace before seeding
    python -m scripts.seed-entries --workspace my-team --clear
"""

import argparse
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def entries_url(base_url: str, workspace: str) -> str:
    """Build the v2 entries endpoint URL for the given workspace."""
    return f"{base_url.rstrip('/')}/apis/intake/v2/workspaces/{workspace}/entries"


# Conversation Data --------------------------------------------------------

CONVERSATION_TOPICS = [
    {
        "topic": "Python debugging help",
        "turns": [
            {
                "user": "I'm getting a weird error in my Python code. It says 'list index out of range' but I can't figure out where.",
                "assistant": "I'd be happy to help you debug that IndexError! To better assist you, could you share the specific code that's causing the error and the full error traceback? The 'list index out of range' error typically occurs when you're trying to access an index that doesn't exist in your list.",
            },
            {
                "user": "Here's my code:\n```python\nnumbers = [1, 2, 3]\nfor i in range(5):\n    print(numbers[i])\n```",
                "assistant": "I found the issue! Your list `numbers` has only 3 elements (indices 0, 1, 2), but your loop runs 5 times (i goes from 0 to 4). When i becomes 3 or 4, you're trying to access `numbers[3]` and `numbers[4]` which don't exist.\n\nHere's the fix:\n```python\nnumbers = [1, 2, 3]\nfor i in range(len(numbers)):  # This ensures i only goes from 0 to 2\n    print(numbers[i])\n```\n\nOr even better, use direct iteration:\n```python\nnumbers = [1, 2, 3]\nfor number in numbers:\n    print(number)\n```",
            },
            {
                "user": "That makes sense! But what if I actually need the index for something else?",
                "assistant": 'Great question! When you need both the index and the value, use the `enumerate()` function. It\'s the Pythonic way to get both:\n\n```python\nnumbers = [1, 2, 3]\nfor i, number in enumerate(numbers):\n    print(f"Index {i}: {number}")\n```\n\nThis will output:\n```\nIndex 0: 1\nIndex 1: 2\nIndex 2: 3\n```\n\nThe `enumerate()` function returns tuples of (index, value) for each item in your list, so you avoid the index out of range error while still having access to both pieces of information.',
            },
            {
                "user": "Perfect! One more question - what if I'm working with a list that might be empty?",
                "assistant": 'Excellent question! Empty lists are a common edge case. Here are a few approaches:\n\n1. **Check if the list is empty first:**\n```python\nnumbers = []\nif numbers:  # This is False for empty lists\n    for i, number in enumerate(numbers):\n        print(f"Index {i}: {number}")\nelse:\n    print("List is empty!")\n```\n\n2. **Use try-except for specific operations:**\n```python\nnumbers = []\ntry:\n    first_item = numbers[0]\n    print(f"First item: {first_item}")\nexcept IndexError:\n    print("No items in the list")\n```\n\n3. **Use get-like methods for safe access:**\n```python\nnumbers = []\n# Safe way to get first item with default\nfirst_item = numbers[0] if numbers else "No items"\nprint(first_item)\n```\n\nThe `enumerate()` and direct iteration approaches handle empty lists gracefully - they simply don\'t execute the loop body.',
            },
            {
                "user": "This is really helpful! I think I understand lists better now. Do you have any tips for avoiding these kinds of errors in general?",
                "assistant": "Absolutely! Here are some best practices to avoid index errors and write more robust Python code:\n\n**1. Prefer iteration over indexing:**\n```python\n# Good\nfor item in my_list:\n    process(item)\n\n# Less preferred\nfor i in range(len(my_list)):\n    process(my_list[i])\n```\n\n**2. Use built-in functions:**\n- `enumerate()` when you need indices\n- `zip()` for parallel iteration\n- `len()` to check bounds\n\n**3. Validate inputs:**\n```python\ndef get_item(lst, index):\n    if 0 <= index < len(lst):\n        return lst[index]\n    return None  # or raise a custom exception\n```\n\n**4. Use list comprehensions and built-ins:**\n```python\n# Instead of manual loops that might have index errors\nresults = [process(item) for item in my_list if condition(item)]\n```\n\n**5. Consider using `get()` method for dictionaries and similar patterns for lists.**\n\nThe key is to write code that's naturally safe by design rather than trying to catch errors after the fact!",
            },
            {
                "user": "These are great tips! I'm going to bookmark this conversation. Thanks so much for your help!",
                "assistant": "You're very welcome! I'm glad I could help you understand list indexing better. Debugging can be frustrating, but you handled it really well by providing the code example - that made all the difference in identifying the issue quickly.\n\nFeel free to come back anytime you have more Python questions. Happy coding, and remember: when in doubt, `print()` statements and the Python debugger are your friends for tracking down tricky issues!",
            },
            {
                "user": "Actually, one quick follow-up. What's this Python debugger you mentioned?",
                "assistant": 'Great question! Python has a built-in debugger called `pdb` (Python Debugger) that\'s incredibly useful for stepping through code and inspecting variables.\n\n**Basic usage:**\n```python\nimport pdb\n\nnumbers = [1, 2, 3]\npdb.set_trace()  # Execution will pause here\nfor i in range(5):\n    print(numbers[i])  # You can inspect this line-by-line\n```\n\n**Key pdb commands:**\n- `n` (next): Execute next line\n- `s` (step): Step into function calls\n- `c` (continue): Continue execution\n- `l` (list): Show current code\n- `p variable_name`: Print variable value\n- `pp variable_name`: Pretty-print variable\n- `q` (quit): Exit debugger\n\n**Modern alternatives:**\n- `breakpoint()` (Python 3.7+) - cleaner than `pdb.set_trace()`\n- IDE debuggers (PyCharm, VS Code) - visual debugging\n- `ipdb` - enhanced debugger with IPython features\n\n**Quick example:**\n```python\nnumbers = [1, 2, 3]\nfor i in range(5):\n    breakpoint()  # Pause here each iteration\n    print(f"About to access index {i}")\n    print(numbers[i])\n```\n\nThis would let you see exactly when `i` becomes problematic!',
            },
            {
                "user": "Wow, I had no idea Python had a built-in debugger! This would have saved me so much time. How do I exit the debugger if I accidentally trigger it?",
                "assistant": "Great question! Getting \"stuck\" in the debugger is a common experience when you're first learning it. Here's how to get out:\n\n**To exit the debugger:**\n1. Type `q` and press Enter - this quits the debugger\n2. If that doesn't work, try `Ctrl+C` (sometimes needed if the debugger is unresponsive)\n3. As a last resort, `Ctrl+Z` (on Unix/Mac) or `Ctrl+Break` (Windows) to force quit\n\n**Pro tips to avoid getting stuck:**\n```python\n# Remove debugger statements when done debugging\n# breakpoint()  # Comment out or delete\n\n# Or use conditional breakpoints\nif some_condition:\n    breakpoint()\n\n# Environment variable to disable all breakpoints\n# Set PYTHONBREAKPOINT=0 to disable all breakpoint() calls\n```\n\n**If you're in an interactive session:**\n- The debugger will show `(Pdb)` prompt\n- Type `c` to continue execution\n- Type `q` to quit back to normal Python prompt\n\n**In IDEs:**\n- Usually there's a \"Stop\" or \"Terminate\" button\n- Or use the IDE's keyboard shortcut (often Shift+F5)\n\n**Remember:** The debugger is pausing execution, not breaking anything. Your program will resume normally once you continue or quit. Don't panic if you accidentally trigger it - just type `q` and you're back to normal!",
            },
            {
                "user": "Perfect! This has been incredibly educational. I feel much more confident about debugging Python now.",
                "assistant": "That's fantastic to hear! You've made great progress - from fixing a specific IndexError to learning about defensive programming practices and debugging tools. That's exactly the kind of learning journey that will make you a stronger developer.\n\nRemember these key takeaways:\n- Use `enumerate()` and direct iteration when possible\n- Validate inputs and handle edge cases\n- The debugger (`breakpoint()`) is your friend for complex issues\n- Don't be afraid to add `print()` statements for quick debugging\n\nYou've got this! Debugging is a skill that improves with practice, and you're asking all the right questions. Keep experimenting and don't hesitate to reach out when you encounter new challenges. Happy coding! 🐍✨",
            },
            {
                "user": "One last thing - do you have any recommendations for Python debugging tools beyond the built-in debugger?",
                "assistant": "Absolutely! Here are some excellent debugging tools beyond `pdb`:\n\n**Enhanced Debuggers:**\n- **ipdb** - Like pdb but with IPython features (syntax highlighting, tab entry)\n- **pudb** - Full-screen console debugger with a nice UI\n- **web-pdb** - Debug in your browser instead of terminal\n\n**IDE Integration:**\n- **PyCharm** - Excellent visual debugger with breakpoints, variable inspection\n- **VS Code** - Great Python debugging with the Python extension\n- **Thonny** - Beginner-friendly IDE with step-through debugging\n\n**Profiling & Performance:**\n- **cProfile** - Built-in performance profiler\n- **line_profiler** - Line-by-line performance analysis\n- **memory_profiler** - Track memory usage\n\n**Logging & Monitoring:**\n- **loguru** - Much better than standard logging\n- **rich** - Beautiful console output and tracebacks\n- **icecream** - Better than print() for debugging\n\n**Quick example with icecream:**\n```python\nfrom icecream import ic\nnumbers = [1, 2, 3]\nfor i in range(5):\n    ic(i, len(numbers))  # Shows: i=3, len(numbers)=3\n    if i < len(numbers):\n        ic(numbers[i])\n```\n\nStart with your IDE's debugger for visual debugging, and icecream for quick print-style debugging. Happy debugging! 🛠️",
            },
        ],
    },
    {
        "topic": "React performance optimization",
        "turns": [
            {
                "user": "My React app is getting really slow, especially when I type in forms. Any ideas what might be causing this?",
                "assistant": "Slow form typing in React is usually caused by unnecessary re-renders. Here are the most common culprits:\n\n1. **Re-rendering the entire component on each keystroke**\n2. **Heavy computations running on every render**\n3. **Inefficient state management**\n4. **Missing memoization**\n\nCould you share a bit about your form setup? Specifically:\n- Are you using controlled components (value + onChange)?\n- How are you managing form state?\n- Are there any complex calculations or API calls happening during typing?",
            },
            {
                "user": "I'm using controlled components with useState for each field. I have about 10 fields and some validation that runs on every change.",
                "assistant": "Ah, that's likely the issue! Running validation on every keystroke is expensive. Here are some optimizations:\n\n**1. Debounce validation:**\n```jsx\nimport { useMemo, useState } from 'react';\nimport { useDebounce } from 'use-debounce';\n\nfunction MyForm() {\n  const [email, setEmail] = useState('');\n  const [debouncedEmail] = useDebounce(email, 300); // 300ms delay\n  \n  const emailError = useMemo(() => {\n    return validateEmail(debouncedEmail);\n  }, [debouncedEmail]);\n\n  return (\n    <input \n      value={email} \n      onChange={(e) => setEmail(e.target.value)}\n    />\n  );\n}\n```\n\n**2. Use React Hook Form (recommended):**\n```jsx\nimport { useForm } from 'react-hook-form';\n\nfunction OptimizedForm() {\n  const { register, handleSubmit, formState: { errors } } = useForm();\n  \n  return (\n    <form onSubmit={handleSubmit(onSubmit)}>\n      <input {...register('email', { required: true })} />\n      {errors.email && <span>Email is required</span>}\n    </form>\n  );\n}\n```\n\nReact Hook Form minimizes re-renders by using uncontrolled components under the hood. Would you like me to show you how to migrate your current form?",
            },
            {
                "user": "That React Hook Form looks interesting! How would I migrate my current validation logic to it?",
                "assistant": "Great choice! React Hook Form will significantly improve your performance. Here's how to migrate your validation:\n\n**Current pattern (slow):**\n```jsx\nconst [email, setEmail] = useState('');\nconst [errors, setErrors] = useState({});\n\n// This runs on every keystroke - slow!\nconst validateEmail = (value) => {\n  if (!value) return 'Email required';\n  if (!/\\S+@\\S+\\.\\S+/.test(value)) return 'Invalid email';\n  return '';\n};\n\nconst emailError = validateEmail(email);\n```\n\n**Migrated to React Hook Form:**\n```jsx\nimport { useForm } from 'react-hook-form';\n\nfunction MyForm() {\n  const { \n    register, \n    handleSubmit, \n    formState: { errors },\n    watch // Optional: for dependent fields\n  } = useForm({\n    mode: 'onBlur', // Validate on blur, not on change\n  });\n\n  const onSubmit = (data) => {\n    console.log(data); // All form data\n  };\n\n  return (\n    <form onSubmit={handleSubmit(onSubmit)}>\n      <input\n        {...register('email', {\n          required: 'Email is required',\n          pattern: {\n            value: /\\S+@\\S+\\.\\S+/,\n            message: 'Invalid email format'\n          }\n        })}\n      />\n      {errors.email && <span>{errors.email.message}</span>}\n      \n      <input\n        {...register('name', {\n          required: 'Name is required',\n          minLength: {\n            value: 2,\n            message: 'Name must be at least 2 characters'\n          }\n        })}\n      />\n      {errors.name && <span>{errors.name.message}</span>}\n      \n      <button type=\"submit\">Submit</button>\n    </form>\n  );\n}\n```\n\n**For custom validation functions:**\n```jsx\nconst validatePassword = (value) => {\n  if (value.length < 8) return 'Password must be 8+ characters';\n  if (!/(?=.*[0-9])/.test(value)) return 'Must contain a number';\n  return true;\n};\n\n<input\n  {...register('password', {\n    required: 'Password required',\n    validate: validatePassword\n  })}\n/>\n```\n\nThe key benefits: validation only runs when needed, and the form doesn't re-render on every keystroke!",
            },
            {
                "user": "This is exactly what I needed! One more question - what about complex validation that depends on multiple fields?",
                "assistant": "Excellent question! Cross-field validation is where React Hook Form really shines. Here are the best approaches:\n\n**1. Using `watch` for dependent validation:**\n```jsx\nfunction MyForm() {\n  const { register, handleSubmit, watch, formState: { errors } } = useForm();\n  \n  const password = watch('password'); // Watch password field\n  \n  return (\n    <form onSubmit={handleSubmit(onSubmit)}>\n      <input\n        {...register('password', { required: 'Password required' })}\n        type=\"password\"\n      />\n      \n      <input\n        {...register('confirmPassword', {\n          required: 'Please confirm password',\n          validate: (value) => \n            value === password || 'Passwords do not match'\n        })}\n        type=\"password\"\n      />\n      {errors.confirmPassword && <span>{errors.confirmPassword.message}</span>}\n    </form>\n  );\n}\n```\n\n**2. Complex multi-field validation:**\n```jsx\nconst validateAddressFields = (data) => {\n  const { country, state, zipCode } = data;\n  \n  if (country === 'US' && !state) {\n    return 'State is required for US addresses';\n  }\n  \n  if (country === 'US' && !/^\\d{5}(-\\d{4})?$/.test(zipCode)) {\n    return 'Invalid US ZIP code format';\n  }\n  \n  return true;\n};\n\n<input\n  {...register('zipCode', {\n    validate: (value, formValues) => validateAddressFields(formValues)\n  })}\n/>\n```\n\n**3. Real-time validation with `trigger`:**\n```jsx\nconst { register, trigger, watch } = useForm();\nconst password = watch('password');\n\n// Re-validate confirm password when password changes\nReact.useEffect(() => {\n  if (password) {\n    trigger('confirmPassword'); // Re-run validation\n  }\n}, [password, trigger]);\n```\n\n**4. Schema validation with Yup (for complex cases):**\n```jsx\nimport { yupResolver } from '@hookform/resolvers/yup';\nimport * as yup from 'yup';\n\nconst schema = yup.object({\n  email: yup.string().email().required(),\n  password: yup.string().min(8).required(),\n  confirmPassword: yup.string()\n    .oneOf([yup.ref('password')], 'Passwords must match')\n    .required()\n});\n\nconst { register } = useForm({\n  resolver: yupResolver(schema)\n});\n```\n\nThe beauty is that validation only runs when necessary, not on every keystroke!",
            },
            {
                "user": "Perfect! This will definitely solve my performance issues. Thanks for the detailed examples!",
                "assistant": "You're very welcome! You're going to see a huge performance improvement with these changes. React Hook Form typically reduces re-renders by 80-90% compared to traditional controlled components.\n\n**Quick recap of what you're gaining:**\n- ✅ No re-renders on every keystroke\n- ✅ Validation only when needed (onBlur, onSubmit, or triggered)\n- ✅ Built-in performance optimizations\n- ✅ Cleaner code with less boilerplate\n- ✅ Better user experience\n\n**Pro tip:** Start with `mode: 'onBlur'` for the best balance of performance and UX. You can always switch to `mode: 'onChange'` for specific fields if needed.\n\nFeel free to reach out if you run into any issues during the migration. Good luck with your optimization! 🚀",
            },
            {
                "user": "Just implemented it and wow, the difference is incredible! One more question - any tips for optimizing the rest of my React app?",
                "assistant": "That's awesome to hear! 🎉 Since you've tackled forms, here are the next biggest React performance wins:\n\n**1. Memoization (biggest impact):**\n```jsx\n// Memoize expensive components\nconst ExpensiveComponent = React.memo(({ data }) => {\n  return <div>{processData(data)}</div>;\n});\n\n// Memoize expensive calculations\nconst processedData = useMemo(() => {\n  return expensiveCalculation(rawData);\n}, [rawData]);\n\n// Memoize callbacks\nconst handleClick = useCallback((id) => {\n  onItemClick(id);\n}, [onItemClick]);\n```\n\n**2. Virtual scrolling for large lists:**\n```jsx\nimport { FixedSizeList as List } from 'react-window';\n\n// Instead of rendering 1000+ items\n<List height={600} itemCount={items.length} itemSize={50}>\n  {({ index, style }) => (\n    <div style={style}>{items[index]}</div>\n  )}\n</List>\n```\n\n**3. Code splitting & lazy loading:**\n```jsx\nconst LazyComponent = lazy(() => import('./HeavyComponent'));\n\n<Suspense fallback={<div>Loading...</div>}>\n  <LazyComponent />\n</Suspense>\n```\n\n**4. Image optimization:**\n```jsx\n// Use next/image or similar\n<img loading=\"lazy\" src={src} alt={alt} />\n```\n\n**5. Avoid inline objects/functions:**\n```jsx\n// Bad - creates new object on every render\n<Component style={{margin: 10}} />\n\n// Good - stable reference\nconst styles = {margin: 10};\n<Component style={styles} />\n```\n\nStart with memoization - it'll give you the biggest wins! 🚀",
            },
            {
                "user": "Great tips! I'm particularly interested in the memoization approach. When should I use React.memo vs useMemo vs useCallback?",
                "assistant": "Excellent question! These three are often confused. Here's when to use each:\n\n**React.memo - Component-level memoization:**\n```jsx\n// Use when props don't change often\nconst ExpensiveChild = React.memo(({ data, onAction }) => {\n  return <div>{expensiveOperation(data)}</div>;\n});\n\n// Only re-renders when data or onAction changes\n// Skip if parent re-renders but props stay the same\n```\n\n**useMemo - Value memoization:**\n```jsx\n// Use for expensive calculations\nfunction MyComponent({ items, searchTerm }) {\n  const filteredItems = useMemo(() => {\n    return items.filter(item => \n      item.name.toLowerCase().includes(searchTerm.toLowerCase())\n    );\n  }, [items, searchTerm]); // Only recalculate when these change\n  \n  return <div>{filteredItems.map(...)}</div>;\n}\n```\n\n**useCallback - Function memoization:**\n```jsx\n// Use when passing functions to memoized children\nfunction Parent({ items }) {\n  const handleClick = useCallback((id) => {\n    // This function won't be recreated on every render\n    setSelectedId(id);\n  }, []); // Dependencies array\n  \n  return (\n    <div>\n      {items.map(item => \n        <MemoizedChild \n          key={item.id} \n          item={item} \n          onClick={handleClick} // Stable reference\n        />\n      )}\n    </div>\n  );\n}\n```\n\n**Quick decision tree:**\n- **React.memo**: Component renders expensive UI\n- **useMemo**: Expensive calculation/transformation\n- **useCallback**: Function passed to memoized children\n\n**Pro tip:** Don't over-memoize! Only use when you have actual performance issues. React is already pretty fast! 🎯",
            },
            {
                "user": "This is super helpful! One thing I'm struggling with is bundle size. My app takes forever to load initially. Any suggestions?",
                "assistant": 'Bundle size is a huge factor in initial load times! Here are the most effective strategies:\n\n**1. Code Splitting (biggest impact):**\n```jsx\n// Split routes\nconst Home = lazy(() => import(\'./pages/Home\'));\nconst Dashboard = lazy(() => import(\'./pages/Dashboard\'));\nconst Settings = lazy(() => import(\'./pages/Settings\'));\n\n<Routes>\n  <Route path="/" element={\n    <Suspense fallback={<Loading />}>\n      <Home />\n    </Suspense>\n  } />\n</Routes>\n```\n\n**2. Dynamic imports for heavy libraries:**\n```jsx\n// Load chart library only when needed\nconst loadChart = async () => {\n  const { Chart } = await import(\'chart.js\');\n  return Chart;\n};\n\n// Use in component\nconst handleShowChart = async () => {\n  const Chart = await loadChart();\n  // Use Chart here\n};\n```\n\n**3. Bundle analysis:**\n```bash\n# Webpack Bundle Analyzer\nnpm install --save-dev webpack-bundle-analyzer\n\n# Or for Create React App\nnpm install --save-dev source-map-explorer\nnpm run build\nnpm run analyze\n```\n\n**4. Tree shaking (import only what you need):**\n```jsx\n// Bad - imports entire library\nimport _ from \'lodash\';\n\n// Good - imports only what you need\nimport { debounce } from \'lodash\';\n// Or even better\nimport debounce from \'lodash/debounce\';\n```\n\n**5. Optimize dependencies:**\n```jsx\n// Replace heavy libraries with lighter alternatives\n// moment.js (67KB) → date-fns (13KB)\n// lodash (69KB) → native JS methods when possible\n// entire icon library → specific icons only\n```\n\n**6. Preloading critical resources:**\n```html\n<link rel="preload" href="/fonts/main.woff2" as="font" type="font/woff2" crossorigin>\n<link rel="preload" href="/critical.css" as="style">\n```\n\nStart with bundle analysis to see what\'s actually taking up space - you might be surprised! 📊',
            },
            {
                "user": "Bundle analysis revealed that Chart.js is taking up 40% of my bundle! But I only use it on one admin page. How can I optimize this?",
                "assistant": "Perfect example of where code splitting shines! Chart.js is a beast (300KB+), but you can easily load it only when needed:\n\n**1. Route-level splitting (easiest):**\n```jsx\n// AdminDashboard.jsx - split the entire page\nconst AdminDashboard = lazy(() => import('./pages/AdminDashboard'));\n\n<Route path=\"/admin\" element={\n  <Suspense fallback={<AdminLoading />}>\n    <AdminDashboard />\n  </Suspense>\n} />\n```\n\n**2. Component-level splitting (more granular):**\n```jsx\n// ChartComponent.jsx - split just the chart\nconst ChartComponent = lazy(() => import('./components/ChartComponent'));\n\nfunction AdminPage() {\n  const [showChart, setShowChart] = useState(false);\n  \n  return (\n    <div>\n      <button onClick={() => setShowChart(true)}>Show Analytics</button>\n      {showChart && (\n        <Suspense fallback={<div>Loading chart...</div>}>\n          <ChartComponent data={chartData} />\n        </Suspense>\n      )}\n    </div>\n  );\n}\n```\n\n**3. Dynamic import with loading state:**\n```jsx\nfunction AdminPage() {\n  const [Chart, setChart] = useState(null);\n  const [loading, setLoading] = useState(false);\n  \n  const loadChart = async () => {\n    setLoading(true);\n    try {\n      const chartModule = await import('chart.js/auto');\n      setChart(() => chartModule.default);\n    } finally {\n      setLoading(false);\n    }\n  };\n  \n  return (\n    <div>\n      {!Chart && (\n        <button onClick={loadChart} disabled={loading}>\n          {loading ? 'Loading...' : 'Show Analytics'}\n        </button>\n      )}\n      {Chart && <MyChart Chart={Chart} />}\n    </div>\n  );\n}\n```\n\n**4. Consider lighter alternatives:**\n```jsx\n// Chart.js is feature-rich but heavy\n// Recharts (smaller, React-specific)\nimport { LineChart, Line } from 'recharts';\n\n// Or even lighter solutions\nimport { Sparklines, SparklinesLine } from 'react-sparklines';\n```\n\n**Pro tip:** After splitting Chart.js out, your main bundle should be 40% smaller, and your admin page will load Chart.js in parallel while users navigate to it. Win-win! 🎯\n\nWhat does your bundle analysis show as the next biggest culprit?",
            },
            {
                "user": "Amazing! After implementing route splitting, my initial load went from 8 seconds to 2 seconds. The next biggest issue seems to be images - they're really slowing things down.",
                "assistant": 'Fantastic progress! 🚀 Images are often the silent performance killer. Here\'s how to optimize them:\n\n**1. Image format optimization:**\n```jsx\n// Modern formats with fallbacks\n<picture>\n  <source srcSet="image.avif" type="image/avif" />\n  <source srcSet="image.webp" type="image/webp" />\n  <img src="image.jpg" alt="Description" />\n</picture>\n\n// Or use Next.js Image component (handles this automatically)\nimport Image from \'next/image\';\n<Image src="/image.jpg" width={400} height={300} alt="Description" />\n```\n\n**2. Lazy loading (huge impact):**\n```jsx\n// Native lazy loading\n<img src="image.jpg" loading="lazy" alt="Description" />\n\n// Or React library\nimport { LazyLoadImage } from \'react-lazy-load-image-component\';\n<LazyLoadImage src="image.jpg" alt="Description" />\n```\n\n**3. Responsive images:**\n```jsx\n// Serve different sizes based on viewport\n<img\n  srcSet="\n    image-small.jpg 400w,\n    image-medium.jpg 800w,\n    image-large.jpg 1200w\n  "\n  sizes="(max-width: 600px) 400px, (max-width: 1000px) 800px, 1200px"\n  src="image-medium.jpg"\n  alt="Description"\n/>\n```\n\n**4. Image compression & tools:**\n```bash\n# Squoosh (Google) - online tool\n# ImageOptim - Mac app\n# TinyPNG - online compression\n\n# Or automate with webpack\nnpm install --save-dev imagemin-webpack-plugin\n```\n\n**5. Critical images vs non-critical:**\n```jsx\n// Preload critical above-the-fold images\n<link rel="preload" as="image" href="hero-image.jpg" />\n\n// Lazy load everything else\n<img src="below-fold.jpg" loading="lazy" alt="Description" />\n```\n\n**6. Progressive loading:**\n```jsx\n// Show low-quality placeholder first\nconst [imageLoaded, setImageLoaded] = useState(false);\n\n<div style={{ backgroundImage: imageLoaded ? \'none\' : \'url(tiny-blur.jpg)\' }}>\n  <img \n    src="full-quality.jpg" \n    onLoad={() => setImageLoaded(true)}\n    style={{ opacity: imageLoaded ? 1 : 0 }}\n  />\n</div>\n```\n\n**Quick wins to try first:**\n1. Add `loading="lazy"` to all below-the-fold images\n2. Convert large images to WebP format\n3. Compress images (aim for <100KB per image)\n4. Use responsive images for different screen sizes\n\nYou should see another significant improvement! What\'s your current image strategy? 📸',
            },
            {
                "user": "This is incredible - my Lighthouse score went from 45 to 92! One last question: any tips for maintaining good performance as the app grows?",
                "assistant": 'That\'s an amazing improvement! 🎉 From 45 to 92 is fantastic. Here\'s how to keep it that way as you scale:\n\n**1. Performance monitoring:**\n```jsx\n// Core Web Vitals tracking\nimport { getCLS, getFID, getFCP, getLCP, getTTFB } from \'web-vitals\';\n\nfunction sendToAnalytics(metric) {\n  // Send to your analytics service\n  console.log(metric);\n}\n\ngetCLS(sendToAnalytics);\ngetFID(sendToAnalytics);\ngetFCP(sendToAnalytics);\ngetLCP(sendToAnalytics);\ngetTTFB(sendToAnalytics);\n```\n\n**2. Performance budgets & CI:**\n```json\n// In package.json - fail builds if bundle gets too big\n"scripts": {\n  "build": "react-scripts build && npm run check-size",\n  "check-size": "bundlesize"\n},\n"bundlesize": [\n  {\n    "path": "./build/static/js/*.js",\n    "maxSize": "300kb"\n  }\n]\n```\n\n**3. Regular audits:**\n```bash\n# Automate Lighthouse in CI\nnpm install -g @lhci/cli\nlhci autorun\n\n# Bundle analysis on every PR\nnpm run build && npm run analyze\n```\n\n**4. Performance-first development habits:**\n```jsx\n// Always consider performance impact\n// ❌ Adding heavy library for one function\nimport _ from \'lodash\'; // 69KB for one function\n\n// ✅ Write the function yourself or use smaller alternative\nconst debounce = (fn, delay) => { /* implementation */ };\n\n// ❌ Large state objects\nconst [appState, setAppState] = useState(massiveObject);\n\n// ✅ Split state logically\nconst [user, setUser] = useState();\nconst [settings, setSettings] = useState();\n```\n\n**5. Team guidelines:**\n```markdown\n## Performance Checklist\n- [ ] New images are compressed and lazy-loaded\n- [ ] New dependencies are justified (check bundle impact)\n- [ ] New routes are code-split\n- [ ] Heavy computations are memoized\n- [ ] Lighthouse score stays above 90\n```\n\n**6. Automated performance testing:**\n```javascript\n// In your test suite\ntest(\'Homepage loads in under 2 seconds\', async () => {\n  const start = Date.now();\n  await render(<HomePage />);\n  expect(Date.now() - start).toBeLessThan(2000);\n});\n```\n\n**Pro tips for sustainable performance:**\n- Make Lighthouse audits part of your PR process\n- Set up bundle size alerts\n- Regular "performance debt" cleanup sessions\n- Celebrate performance wins with the team! 🎯\n\nYou\'ve built something awesome - keep it fast! What\'s your next performance challenge going to be?',
            },
        ],
    },
]


# Tool Calling Examples --------------------------------------------------------

TOOL_CALLING_EXAMPLES = [
    {
        "user_query": "What's the weather like in San Francisco today?",
        "request": {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "What's the weather like in San Francisco today?"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get current weather information for a location",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string", "description": "City name or coordinates"},
                                "units": {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "fahrenheit"},
                            },
                            "required": ["location"],
                        },
                    },
                }
            ],
        },
        "response": {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc123",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"location": "San Francisco", "units": "fahrenheit"}',
                                },
                            }
                        ],
                    }
                }
            ]
        },
        "has_error": False,
    },
    {
        "user_query": "Can you analyze this CSV data and tell me the average sales?",
        "request": {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "user",
                    "content": "Can you analyze this CSV data and tell me the average sales?\n\nproduct,sales\nWidget A,1500\nWidget B,2300\nWidget C,1800",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "analyze_csv_data",
                        "description": "Analyze CSV data and compute statistics",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "csv_content": {"type": "string", "description": "Raw CSV data"},
                                "operations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Statistical operations to perform",
                                },
                            },
                            "required": ["csv_content", "operations"],
                        },
                    },
                }
            ],
        },
        "response": {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_def456",
                                "type": "function",
                                "function": {
                                    "name": "analyze_csv_data",
                                    "arguments": '{"csv_content": "product,sales\\nWidget A,1500\\nWidget B,2300\\nWidget C,1800", "operations": ["mean", "sum", "count"]}',
                                },
                            }
                        ],
                    }
                }
            ]
        },
        "has_error": False,
    },
    {
        "user_query": "Send an email to john@example.com about the project update",
        "request": {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Send an email to john@example.com about the project update"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "send_email",
                        "description": "Send an email message",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "to": {"type": "string", "description": "Recipient email address"},
                                "subject": {"type": "string", "description": "Email subject"},
                                "body": {"type": "string", "description": "Email body content"},
                            },
                            "required": ["to", "subject", "body"],
                        },
                    },
                }
            ],
        },
        "response": {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I'll send an email to john@example.com about the project update.",
                        "tool_calls": [
                            {
                                "id": "call_ghi789",
                                "type": "function",
                                "function": {
                                    "name": "send_email",
                                    "arguments": '{"to": "john@example.com", "subject": "Project Update", "body": "Hi John,\\n\\nI wanted to provide you with an update on our current project status. Please let me know if you have any questions or need additional details.\\n\\nBest regards"}',
                                },
                            }
                        ],
                    }
                }
            ]
        },
        "has_error": True,  # Missing required information - should ask for specifics
        "reviewer_comment": "Model should have asked for specific project details and update content before sending email.",
    },
    {
        "user_query": "Calculate the compound interest for $1000 at 5% for 10 years",
        "request": {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Calculate the compound interest for $1000 at 5% for 10 years"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "calculate_compound_interest",
                        "description": "Calculate compound interest",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "principal": {"type": "number", "description": "Initial amount"},
                                "rate": {"type": "number", "description": "Annual interest rate (as decimal)"},
                                "time": {"type": "number", "description": "Time period in years"},
                                "compounds_per_year": {
                                    "type": "number",
                                    "description": "Compounding frequency per year",
                                    "default": 1,
                                },
                            },
                            "required": ["principal", "rate", "time"],
                        },
                    },
                }
            ],
        },
        "response": {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_jkl012",
                                "type": "function",
                                "function": {
                                    "name": "calculate_compound_interest",
                                    "arguments": '{"principal": 1000, "rate": 0.5, "time": 10}',
                                },
                            }
                        ],
                    }
                }
            ]
        },
        "has_error": True,  # Wrong rate (0.5 instead of 0.05)
        "reviewer_comment": "Model used incorrect rate conversion. 5% should be 0.05, not 0.5.",
    },
]


# Query Rewriting Examples --------------------------------------------------------

QUERY_REWRITING_EXAMPLES = [
    {
        "user_query": "I'm trying to figure out how to make my code run faster when I'm doing machine learning stuff with Python and I think there might be some libraries or techniques that could help but I'm not sure which ones are best for my specific use case",
        "request": {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a query rewriting assistant. Rewrite the user's complex question into a cleaner, more focused query suitable for retrieval systems. Extract the key concepts and present them in a clear, searchable format.",
                },
                {
                    "role": "user",
                    "content": "I'm trying to figure out how to make my code run faster when I'm doing machine learning stuff with Python and I think there might be some libraries or techniques that could help but I'm not sure which ones are best for my specific use case",
                },
            ],
        },
        "response": {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Python machine learning performance optimization libraries and techniques",
                    }
                }
            ]
        },
        "has_error": False,
    },
    {
        "user_query": "My manager wants me to create some kind of dashboard or visualization thing that shows our sales data but also needs to be interactive and I'm not really sure what tools to use or how to get started with this kind of project",
        "request": {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a query rewriting assistant. Rewrite the user's complex question into a cleaner, more focused query suitable for retrieval systems. Extract the key concepts and present them in a clear, searchable format.",
                },
                {
                    "role": "user",
                    "content": "My manager wants me to create some kind of dashboard or visualization thing that shows our sales data but also needs to be interactive and I'm not really sure what tools to use or how to get started with this kind of project",
                },
            ],
        },
        "response": {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Interactive sales dashboard creation tools and getting started guide",
                    }
                }
            ]
        },
        "has_error": False,
    },
    {
        "user_query": "So I've been working on this React project and I keep running into issues with state management and I know there are different approaches like Redux and Context API but I'm confused about when to use which one and also how to handle async data fetching in a clean way",
        "request": {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a query rewriting assistant. Rewrite the user's complex question into a cleaner, more focused query suitable for retrieval systems. Extract the key concepts and present them in a clear, searchable format.",
                },
                {
                    "role": "user",
                    "content": "So I've been working on this React project and I keep running into issues with state management and I know there are different approaches like Redux and Context API but I'm confused about when to use which one and also how to handle async data fetching in a clean way",
                },
            ],
        },
        "response": {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "React state management: Redux vs Context API comparison and async data fetching best practices",
                    }
                }
            ]
        },
        "has_error": False,
    },
    {
        "user_query": "I need help understanding databases and SQL and all that stuff because I'm working on a web application that needs to store user information and product data and I want to make sure I design the database correctly from the beginning so I don't run into problems later",
        "request": {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a query rewriting assistant. Rewrite the user's complex question into a cleaner, more focused query suitable for retrieval systems. Extract the key concepts and present them in a clear, searchable format.",
                },
                {
                    "role": "user",
                    "content": "I need help understanding databases and SQL and all that stuff because I'm working on a web application that needs to store user information and product data and I want to make sure I design the database correctly from the beginning so I don't run into problems later",
                },
            ],
        },
        "response": {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Database design best practices for web applications with user and product data",
                    }
                }
            ]
        },
        "has_error": True,  # Too generic, should preserve more specific context
        "reviewer_comment": "The rewritten query is too generic. Should preserve context about SQL learning and avoiding future problems.",
    },
]


CLEAR_PAGE_SIZE = 100
# Bounds the list+delete loop so a misbehaving server cannot loop forever.
# At CLEAR_PAGE_SIZE=100 this covers 100k entries before we give up.
MAX_CLEAR_PAGES = 1000


def clear_entries_via_api(api_url: str, timeout: int = 30) -> None:
    """Delete every entry in the workspace via the v2 API."""
    logger.info("🧹 Deleting all entries at %s", api_url)

    deleted = 0
    with httpx.Client(timeout=timeout) as client:
        for _ in range(MAX_CLEAR_PAGES):
            # Always page=1: each iteration deletes the current page, so the next
            # "first page" is the next batch of still-existing entries.
            list_resp = client.get(api_url, params={"page": 1, "page_size": CLEAR_PAGE_SIZE})
            list_resp.raise_for_status()
            entries = list_resp.json().get("data") or []
            if not entries:
                break

            for entry in entries:
                entry_id = entry["id"]
                del_resp = client.delete(f"{api_url.rstrip('/')}/{entry_id}")
                del_resp.raise_for_status()
                deleted += 1
        else:
            raise RuntimeError(
                f"clear_entries_via_api exceeded {MAX_CLEAR_PAGES} pages "
                f"(~{MAX_CLEAR_PAGES * CLEAR_PAGE_SIZE} entries); "
                "deletes may not be taking effect."
            )

    logger.info("✅ Deleted %d entries", deleted)


# User Feedback Data --------------------------------------------------------

# User feedback includes: thumbs up/down, ratings (1-5), opinions, and user-provided rewrites
USER_FEEDBACK_EXAMPLES = [
    {"type": "thumbs_up", "payload": {"thumb": "up", "opinion": "This was really helpful! Exactly what I needed."}},
    {"type": "thumbs_up", "payload": {"thumb": "up", "opinion": "Great explanation, very clear and detailed."}},
    {"type": "thumbs_up", "payload": {"thumb": "up", "opinion": "Perfect! This solved my problem immediately."}},
    {"type": "thumbs_down", "payload": {"thumb": "down", "opinion": "This doesn't really answer my question."}},
    {"type": "thumbs_down", "payload": {"thumb": "down", "opinion": "Too complicated, I need a simpler explanation."}},
    {
        "type": "rewrite",
        "payload": {
            "thumb": "down",
            "opinion": "Close but not quite right.",
            "rewrite": "Here's a better version: The main issue is that you need to check the array bounds before accessing elements. Use `if (index < array.length)` to prevent errors.",
        },
    },
    {
        "type": "rewrite",
        "payload": {
            "thumb": "down",
            "opinion": "Good start but missing important details.",
            "rewrite": "Your explanation is correct, but you should also mention that React Hook Form handles form validation more efficiently by reducing re-renders, which is the main performance benefit.",
        },
    },
    {"type": "rating", "payload": {"rating": 4.5, "opinion": "Very helpful response, just missing a small detail."}},
    {"type": "rating", "payload": {"rating": 5.0, "opinion": "Excellent! This is exactly what I was looking for."}},
    {"type": "rating", "payload": {"rating": 2.0, "opinion": "Somewhat helpful but not comprehensive enough."}},
]


def create_user_feedback_event_data() -> Dict[str, Any]:
    """Create realistic user feedback event data for API."""
    feedback = random.choice(USER_FEEDBACK_EXAMPLES)

    # Create event data matching UserFeedbackEvent schema
    event_data: Dict[str, Any] = {"event_type": "user_feedback", "created_at": datetime.now(timezone.utc).isoformat()}

    # Add feedback fields based on the type
    payload = feedback["payload"]
    if isinstance(payload, dict):
        if payload.get("thumb"):
            event_data["thumb"] = str(payload["thumb"])
        if payload.get("rating"):
            event_data["rating"] = float(payload["rating"])
        if payload.get("opinion"):
            event_data["opinion"] = str(payload["opinion"])
        if payload.get("rewrite"):
            event_data["rewrite"] = str(payload["rewrite"])

    # Return EventsCreate format with events array
    return {"events": [event_data]}


def add_user_feedback_via_api(api_url: str, entry_id: str, timeout: int = 30) -> bool:
    """Add user feedback event via API call."""
    events_url = f"{api_url.rstrip('/')}/{entry_id}/events"

    try:
        feedback_data = create_user_feedback_event_data()

        with httpx.Client(timeout=timeout) as client:
            response = client.post(events_url, json=feedback_data)
            response.raise_for_status()  # Let it error on 404 or other failures

            logger.info("✅ Added user feedback for entry %s", entry_id)
            return True

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.error("❌ Events endpoint not found for entry %s. URL: %s", entry_id, events_url)
        else:
            logger.error("❌ Failed to add user feedback for %s: HTTP %s", entry_id, e.response.status_code)
        return False
    except Exception as e:
        logger.error("❌ Failed to add user feedback for %s: %s", entry_id, e)
        return False


def create_corrected_response_override(original_example: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create a corrected response_override for examples with errors."""
    if not original_example.get("has_error", False):
        return None

    user_query = original_example.get("user_query", "")

    # Email example - should ask for specifics instead of sending
    if "john@example.com" in user_query and "project update" in user_query:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I'd be happy to help you send an email to john@example.com about a project update. However, I need more specific information to create a meaningful email:\n\n1. What specific project are you referring to?\n2. What key updates or milestones should be included?\n3. What's the current status or recent progress?\n4. Are there any specific actions needed from John?\n5. What tone would be appropriate (formal, casual, urgent)?\n\nOnce you provide these details, I can craft a comprehensive and relevant project update email.",
                        "tool_calls": None,
                    }
                }
            ]
        }

    # Compound interest example - fix the rate conversion
    elif "compound interest" in user_query and "$1000" in user_query:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_jkl012",
                                "type": "function",
                                "function": {
                                    "name": "calculate_compound_interest",
                                    "arguments": '{"principal": 1000, "rate": 0.05, "time": 10}',
                                },
                            }
                        ],
                    }
                }
            ]
        }

    # Query rewriting example - preserve more context
    elif "database" in user_query and "SQL" in user_query:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "SQL database design fundamentals for web applications: avoiding common mistakes when storing user and product data",
                    }
                }
            ]
        }

    return None


def add_reviewer_annotation_via_api(
    api_url: str,
    entry_id: str,
    original_example: Optional[Dict[str, Any]] = None,
    reviewer_comment: Optional[str] = None,
    timeout: int = 30,
) -> bool:
    """Add reviewer annotation event via API call."""
    events_url = f"{api_url.rstrip('/')}/{entry_id}/events"

    try:
        # Create reviewer annotation data
        review_payload: Dict[str, Any] = {
            "thumb": "down" if reviewer_comment else "up",
            "opinion": reviewer_comment or "Good response, accurate and helpful.",
        }

        # Note: rewrite field is for end-user suggestions, not reviewer corrections
        # Reviewers use response_override for corrected responses and opinion for comments

        # Add response_override with corrected response if available
        if original_example:
            corrected_response = create_corrected_response_override(original_example)
            if corrected_response:
                review_payload["response_override"] = corrected_response

        event_data = {"event_type": "reviewer_annotation", **review_payload}

        # Wrap in EventsCreate format
        annotation_data = {"events": [event_data]}

        with httpx.Client(timeout=timeout) as client:
            response = client.post(events_url, json=annotation_data)
            response.raise_for_status()  # Let it error on 404 or other failures

            logger.info("✅ Added reviewer annotation for entry %s", entry_id)
            return True

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.error("❌ Events endpoint not found for entry %s. URL: %s", entry_id, events_url)
        else:
            logger.error("❌ Failed to add reviewer annotation for %s: HTTP %s", entry_id, e.response.status_code)
        return False
    except Exception as e:
        logger.error("❌ Failed to add reviewer annotation for %s: %s", entry_id, e)
        return False


# Data Generation Functions --------------------------------------------------------


def _build_context(workspace: str, app_id: str, task_id: str, thread_id: str) -> Dict[str, Any]:
    return {
        "app": f"{workspace}/{app_id}",
        "task": task_id,
        "thread_id": thread_id,
    }


def create_conversational_entry_data(
    workspace: str, app_id: str, task_id: str, thread_id: str, turn_number: int, conversation_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Create entry data for progressive conversation turns.

    The request carries prior turns plus the current user message; the response
    carries the current assistant reply. This matches the request→response shape
    used by generate_test_dataset.create_conversation_threads.
    """
    messages: List[Dict[str, str]] = []
    for i in range(turn_number - 1):
        prior = conversation_data["turns"][i]
        messages.append({"role": "user", "content": prior["user"]})
        messages.append({"role": "assistant", "content": prior["assistant"]})

    current_turn = conversation_data["turns"][turn_number - 1]
    messages.append({"role": "user", "content": current_turn["user"]})

    return {
        "data": {
            "request": {
                "model": "gpt-4",
                "messages": messages,
            },
            "response": {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": current_turn["assistant"],
                        }
                    }
                ]
            },
        },
        "context": _build_context(workspace, app_id, task_id, thread_id),
    }


def create_tool_calling_entry_data(
    workspace: str, app_id: str, task_id: str, thread_id: str, tool_example: Dict[str, Any]
) -> Dict[str, Any]:
    """Create entry data for tool calling examples."""
    return {
        "data": {
            "request": tool_example["request"],
            "response": tool_example["response"],
        },
        "context": _build_context(workspace, app_id, task_id, thread_id),
    }


def create_query_rewriting_entry_data(
    workspace: str, app_id: str, task_id: str, thread_id: str, rewriting_example: Dict[str, Any]
) -> Dict[str, Any]:
    """Create entry data for query rewriting examples."""
    return {
        "data": {
            "request": rewriting_example["request"],
            "response": rewriting_example["response"],
        },
        "context": _build_context(workspace, app_id, task_id, thread_id),
    }


def seed_api_diverse(
    api_url: str,
    workspace: str,
    num_conversations: int = 5,
    num_tool_examples: int = 15,
    num_query_examples: int = 10,
    timeout: int = 30,
) -> None:
    """Seed the API with diverse, realistic entry records (API mode)."""
    logger.info(
        "🌱 Seeding API with diverse entries: %d conversations, %d tool examples, %d query examples to %s",
        num_conversations,
        num_tool_examples,
        num_query_examples,
        api_url,
    )

    successful_requests = 0
    failed_requests = 0

    with httpx.Client(timeout=timeout) as client:
        # 1. Create conversational support entries (10 turns each)
        for conv_idx in range(num_conversations):
            conversation = random.choice(CONVERSATION_TOPICS)
            thread_id = f"conv_thread_{conv_idx + 1}"
            app_id = f"support_client_{(conv_idx % 3) + 1}"

            for turn in range(1, 11):  # 10 turns
                entry_data = create_conversational_entry_data(
                    workspace=workspace,
                    app_id=app_id,
                    task_id="conversational-support",
                    thread_id=thread_id,
                    turn_number=turn,
                    conversation_data=conversation,
                )

                try:
                    response = client.post(api_url, json=entry_data)
                    response.raise_for_status()

                    response_data = response.json()
                    entry_id = response_data.get("id", f"conv_{conv_idx}_{turn}")

                    logger.info("Created conversation entry %s (turn %d/10)", entry_id, turn)
                    successful_requests += 1

                    # Add user feedback on turns 3, 5, and 8
                    if turn in [3, 5, 8]:
                        add_user_feedback_via_api(api_url, entry_id, timeout)

                except Exception as e:
                    logger.error("Error creating conversation entry %d-%d: %s", conv_idx, turn, e)
                    failed_requests += 1

        # 2. Create tool calling entries
        for tool_idx in range(num_tool_examples):
            tool_example = random.choice(TOOL_CALLING_EXAMPLES)
            thread_id = f"tool_thread_{tool_idx + 1}"
            app_id = f"tool_client_{(tool_idx % 2) + 1}"

            entry_data = create_tool_calling_entry_data(
                workspace=workspace,
                app_id=app_id,
                task_id="tool-calling-examples",
                thread_id=thread_id,
                tool_example=tool_example,
            )

            try:
                response = client.post(api_url, json=entry_data)
                response.raise_for_status()

                response_data = response.json()
                entry_id = response_data.get("id", f"tool_{tool_idx}")

                logger.info("Created tool calling entry %s", entry_id)
                successful_requests += 1

                # Add user feedback for some tool examples (30% chance)
                if random.random() < 0.3:
                    add_user_feedback_via_api(api_url, entry_id, timeout)

                # Add reviewer annotation if example has errors
                add_reviewer = bool(tool_example.get("has_error", False))
                reviewer_comment = (
                    str(tool_example.get("reviewer_comment"))
                    if add_reviewer and tool_example.get("reviewer_comment")
                    else None
                )
                if add_reviewer:
                    add_reviewer_annotation_via_api(api_url, entry_id, tool_example, reviewer_comment, timeout)

            except Exception as e:
                logger.error("Error creating tool calling entry %d: %s", tool_idx, e)
                failed_requests += 1

        # 3. Create query rewriting entries
        for query_idx in range(num_query_examples):
            query_example = random.choice(QUERY_REWRITING_EXAMPLES)
            thread_id = f"query_thread_{query_idx + 1}"
            app_id = f"retrieval_client_{(query_idx % 2) + 1}"

            entry_data = create_query_rewriting_entry_data(
                workspace=workspace,
                app_id=app_id,
                task_id="query-rewriting",
                thread_id=thread_id,
                rewriting_example=query_example,
            )

            try:
                response = client.post(api_url, json=entry_data)
                response.raise_for_status()

                response_data = response.json()
                entry_id = response_data.get("id", f"query_{query_idx}")

                logger.info("Created query rewriting entry %s", entry_id)
                successful_requests += 1

                # Add user feedback for some query examples (25% chance)
                if random.random() < 0.25:
                    add_user_feedback_via_api(api_url, entry_id, timeout)

                # Add reviewer annotation if example has errors
                add_reviewer = bool(query_example.get("has_error", False))
                reviewer_comment = (
                    str(query_example.get("reviewer_comment"))
                    if add_reviewer and query_example.get("reviewer_comment")
                    else None
                )
                if add_reviewer:
                    add_reviewer_annotation_via_api(api_url, entry_id, query_example, reviewer_comment, timeout)

            except Exception as e:
                logger.error("Error creating query rewriting entry %d: %s", query_idx, e)
                failed_requests += 1

    logger.info("✅ Successfully created %d diverse entries via API", successful_requests)
    if failed_requests > 0:
        logger.warning("⚠️ Failed to create %d entries", failed_requests)


def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(description="Seed intake service with diverse, realistic entry records")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080",
        help="Base URL of the NeMo Platform gateway (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--workspace",
        default="default",
        help=(
            "Target workspace. Used both as the route segment "
            "(.../workspaces/<workspace>/entries) and in each entry's context.app "
            "(default: default)"
        ),
    )
    parser.add_argument(
        "--conversations", type=int, default=3, help="Number of conversation threads to create (default: 3)"
    )
    parser.add_argument(
        "--tool-examples", type=int, default=10, help="Number of tool calling examples to create (default: 10)"
    )
    parser.add_argument(
        "--query-examples", type=int, default=8, help="Number of query rewriting examples to create (default: 8)"
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds (default: 30)")
    parser.add_argument(
        "--clear", action="store_true", help="Delete all existing entries in the workspace before seeding"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    try:
        api_url = entries_url(args.api_url, args.workspace)

        if args.clear:
            clear_entries_via_api(api_url, args.timeout)

        seed_api_diverse(
            api_url,
            args.workspace,
            args.conversations,
            args.tool_examples,
            args.query_examples,
            args.timeout,
        )
    except KeyboardInterrupt:
        logger.info("🛑 Seeding interrupted by user")
    except Exception as e:
        logger.exception("❌ Seeding failed: %s", str(e))
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
