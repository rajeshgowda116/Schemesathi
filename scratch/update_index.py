import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update navigation Ask AI buttons
content = content.replace(
    '''<button onclick="toggleAIChatDrawer(true)" class="flex items-center gap-2 text-gray-700 hover:text-brand-purple px-4 py-1.5 rounded-full text-sm font-semibold transition-colors">
            <i class="fa-solid fa-wand-magic-sparkles text-xs text-brand-purple"></i> Ask AI
          </button>''',
    '''<a href="chatbot.html" class="flex items-center gap-2 text-gray-700 hover:text-brand-purple px-4 py-1.5 rounded-full text-sm font-semibold transition-colors">
            <i class="fa-solid fa-wand-magic-sparkles text-xs text-brand-purple"></i> Ask AI
          </a>'''
)

content = content.replace(
    '''<button onclick="scrollToAIChatOrOpenDrawer()" class="relative inline-flex items-center gap-2 bg-gradient-to-r from-brand-purple to-indigo-700 hover:from-brand-dark hover:to-indigo-800 text-white px-4 py-2 rounded-full text-sm font-semibold shadow-md shadow-purple-200 transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]">
            <i class="fa-solid fa-wand-magic-sparkles text-amber-300"></i>
            <span class="hidden sm:inline">Ask AI Sathi</span>
            <span class="flex h-2 w-2 relative">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-400"></span>
            </span>
          </button>''',
    '''<a href="chatbot.html" class="relative inline-flex items-center gap-2 bg-gradient-to-r from-brand-purple to-indigo-700 hover:from-brand-dark hover:to-indigo-800 text-white px-4 py-2 rounded-full text-sm font-semibold shadow-md shadow-purple-200 transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]">
            <i class="fa-solid fa-wand-magic-sparkles text-amber-300"></i>
            <span class="hidden sm:inline">Ask AI Sathi</span>
            <span class="flex h-2 w-2 relative">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-400"></span>
            </span>
          </a>'''
)

content = content.replace(
    '''<button onclick="toggleAIChatDrawer(true); toggleMobileMenu();" class="w-full text-left block px-3 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-purple-50 hover:text-brand-purple">
        <i class="fa-solid fa-wand-magic-sparkles w-6 text-brand-purple"></i> Ask AI Assistant
      </button>''',
    '''<a href="chatbot.html" onclick="toggleMobileMenu()" class="block px-3 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-purple-50 hover:text-brand-purple">
        <i class="fa-solid fa-wand-magic-sparkles w-6 text-brand-purple"></i> Ask AI Assistant
      </a>'''
)

content = content.replace(
    '''<button 
              onclick="scrollToAIChatOrOpenDrawer()"
              class="w-full sm:w-auto bg-brand-purple hover:bg-brand-dark text-white px-6 py-3 rounded-xl text-sm font-semibold transition-all flex items-center justify-center gap-2 shadow-sm">
              <i class="fa-solid fa-sparkles text-amber-300"></i>
              <span>Ask AI</span>
            </button>''',
    '''<a 
              href="chatbot.html"
              class="w-full sm:w-auto bg-brand-purple hover:bg-brand-dark text-white px-6 py-3 rounded-xl text-sm font-semibold transition-all flex items-center justify-center gap-2 shadow-sm">
              <i class="fa-solid fa-sparkles text-amber-300"></i>
              <span>Ask AI</span>
            </a>'''
)

content = content.replace(
    '''<li><button onclick="toggleAIChatDrawer(true)" class="hover:text-white transition-colors">Ask AI Assistant</button></li>''',
    '''<li><a href="chatbot.html" class="hover:text-white transition-colors">Ask AI Assistant</a></li>'''
)

# 2. Remove Drawer and Modal HTML
# From <!-- ================= SLIDE-OVER AI CHAT DRAWER ================= --> up to <!-- ================= CITIZEN PROFILE MODAL ================= -->
pattern_modals = r'<!-- ================= SLIDE-OVER AI CHAT DRAWER ================= -->.*?<!-- ================= CITIZEN PROFILE MODAL ================= -->'
replacement_modals = '<!-- ================= CITIZEN PROFILE MODAL ================= -->'
content, count_modals = re.subn(pattern_modals, replacement_modals, content, flags=re.DOTALL)
print(f"Modals HTML stripped: {count_modals}")

# 3. Update Action Buttons in renderSchemes()
old_buttons = '''              <!-- Action Buttons -->
              <div class="flex items-center justify-between gap-2 pt-1">
                <button 
                  onclick="openSchemeModal(${scheme.id})"
                  class="flex-1 bg-brand-light hover:bg-purple-100 text-brand-purple px-3 py-2 rounded-xl text-xs font-bold transition-colors flex items-center justify-center gap-1.5">
                  <i class="fa-regular fa-eye text-xs"></i>
                  <span>Details</span>
                </button>

                <button 
                  onclick="askAIAboutScheme(${scheme.id})"
                  title="Ask AI about this scheme"
                  class="w-9 h-9 rounded-xl bg-purple-50 hover:bg-brand-purple hover:text-white text-brand-purple flex items-center justify-center text-xs transition-colors shrink-0">
                  <i class="fa-solid fa-sparkles text-amber-500"></i>
                </button>

                ${
                  scheme.official_url 
                    ? `<a href="${scheme.official_url}" target="_blank" rel="noopener" title="Official Government Portal" class="w-9 h-9 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-600 flex items-center justify-center text-xs transition-colors shrink-0">
                        <i class="fa-solid fa-arrow-up-right-from-square"></i>
                      </a>` 
                    : ''
                }
              </div>'''

new_buttons = '''              <!-- Action Buttons -->
              <div class="flex items-center justify-between gap-2 pt-1">
                <a 
                  href="chatbot.html?scheme=${encodeURIComponent(scheme.scheme_name)}&id=${scheme.id}"
                  class="flex-1 bg-gradient-to-r from-brand-purple to-indigo-700 hover:from-brand-dark hover:to-indigo-800 text-white px-4 py-2.5 rounded-xl text-xs font-bold shadow-md shadow-purple-200 transition-all flex items-center justify-center gap-2 group-hover:scale-[1.01]">
                  <i class="fa-solid fa-comments text-amber-300 text-sm"></i>
                  <span>Chat with Scheme AI</span>
                  <i class="fa-solid fa-arrow-right text-[10px] opacity-75"></i>
                </a>

                ${
                  scheme.official_url 
                    ? `<a href="${scheme.official_url}" target="_blank" rel="noopener" title="Official Government Portal" class="w-10 h-10 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-600 hover:text-brand-purple flex items-center justify-center text-xs transition-colors shrink-0">
                        <i class="fa-solid fa-arrow-up-right-from-square"></i>
                      </a>` 
                    : ''
                }
              </div>'''

content = content.replace(old_buttons, new_buttons)

# 4. Remove Modal and Drawer JS logic
pattern_js_modal = r'// Scheme Details Modal Logic\s+function openSchemeModal\(schemeId\) \{.*?function clearSchemeContext\(\) \{\s+selectedSchemeContext = null;\s+const contextBar = document\.getElementById\(\'drawer-scheme-context\'\);\s+if \(contextBar\) contextBar\.classList\.add\(\'hidden\'\);\s+\}'
replacement_js_modal = '''// Scheme AI Direct Chat Redirect
    function askAIAboutScheme(schemeId) {
      const scheme = allSchemes.find(s => s.id === schemeId);
      if (scheme) {
        window.location.href = `chatbot.html?scheme=${encodeURIComponent(scheme.scheme_name)}&id=${scheme.id}`;
      } else {
        window.location.href = 'chatbot.html';
      }
    }'''

content, count_js_modal = re.subn(pattern_js_modal, replacement_js_modal, content, flags=re.DOTALL)
print(f"Modal JS stripped: {count_js_modal}")

# 5. Remove Drawer and old Chat JS logic
pattern_js_drawer = r'// Slide-over AI Chat Drawer Logic.*?// Toast Notifications'
replacement_js_drawer = '''// Navigation to Dedicated Scheme AI Chatbot
    function toggleAIChatDrawer() {
      window.location.href = 'chatbot.html';
    }

    function scrollToAIChatOrOpenDrawer() {
      window.location.href = 'chatbot.html';
    }

    function loadChatHistory() {}

    // Toast Notifications'''

content, count_js_drawer = re.subn(pattern_js_drawer, replacement_js_drawer, content, flags=re.DOTALL)
print(f"Drawer JS stripped: {count_js_drawer}")

# 6. Clean unused state variables
content = content.replace('let currentModalScheme = null;\n    let selectedSchemeContext = null;', '// Scheme state\n    // Modal and Drawer replaced by dedicated chatbot.html')

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("index.html updated successfully!")
