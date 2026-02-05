/**
 * Shopping List Manager - Custom Lovelace Card
 * 
 * Uses proper Home Assistant WebSocket API
 * Version: 2.1.0 - Fixed syntax errors
 */

// Category definitions
const CATEGORIES = [
  { id: "fruitveg", emoji: "🥬", name: "Fruit & Vegetables", order: 1 },
  { id: "meat", emoji: "🥩", name: "Meat, Poultry & Seafood", order: 2 },
  { id: "fridge", emoji: "🥛", name: "Fridge, Deli & Eggs", order: 3 },
  { id: "bakery", emoji: "🥖", name: "Bakery", order: 4 },
  { id: "frozen", emoji: "🧊", name: "Frozen", order: 5 },
  { id: "pantry", emoji: "🥫", name: "Pantry", order: 6 },
  { id: "drinks", emoji: "☕", name: "Hot & Cold Drinks", order: 7 },
  { id: "alcohol", emoji: "🍺", name: "Beer, Wine & Cider", order: 8 },
  { id: "health", emoji: "🧴", name: "Health & Body", order: 9 },
  { id: "baby", emoji: "🍼", name: "Baby & Toddler", order: 10 },
  { id: "pets", emoji: "🐾", name: "Pets", order: 11 },
  { id: "household", emoji: "🧹", name: "Household & Cleaning", order: 12 },
  { id: "snacks", emoji: "🍫", name: "Snacks, Treats & Easy Meals", order: 13 },
  { id: "other", emoji: "📦", name: "Other", order: 99 }
];

// Create category lookup map
const CATEGORY_MAP = CATEGORIES.reduce((map, cat) => {
  map[cat.id] = cat;
  return map;
}, {});

class ShoppingListCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    
    // State
    this._hass = null;
    this._config = null;
    this._products = {};
    this._activeList = {};
    this._searchQuery = '';
    this._pollInterval = null;
    this._isLoading = true;
    this._sortBy = 'category'; // 'category' or 'alphabet'
    this._selectedCategory = null; // null = show all
    this._searchDebounceTimer = null;
    this._localImageCache = {}; // Cache for local image lookups
    this._imageListCache = null;  // Cached directory listing from /local/images/shopping_list_manager/
    this._cardSize = 'small'; // 'small' or 'large' - detected from card width
    
    // Settings (load from localStorage or defaults)
    this._settings = this._loadSettings();
  }
  
  /**
   * Load settings from localStorage
   */
  _loadSettings() {
    // Baseline defaults
    const defaults = {
      haptics: 'medium',
      productsPerRow: '3',
      layout: 'grid',
      hideCompleted: false,
      compactHeaders: false,
    };

    // Layer 1: read from the card config (this is what HA restores
    // from the persisted YAML on every page load)
    if (this._config) {
      if (this._config.haptics)              defaults.haptics          = this._config.haptics;
      if (this._config.products_per_row)     defaults.productsPerRow   = String(this._config.products_per_row);
      if (this._config.layout)               defaults.layout           = this._config.layout;
      if (this._config.hide_completed    !== undefined) defaults.hideCompleted  = this._config.hide_completed;
      if (this._config.compact_headers   !== undefined) defaults.compactHeaders = this._config.compact_headers;
    }

    // Layer 2: localStorage ALWAYS WINS - cog settings are the source of truth
    // This keeps settings persistent and instant without needing YAML edits
    const key = this._settingsKey || 'shopping_list_settings_default';
    const saved = localStorage.getItem(key);
    if (saved) {
      try {
        return { ...defaults, ...JSON.parse(saved) };
      } catch (e) {
        console.error('Failed to load settings:', e);
      }
    }

    return defaults;
  }
  
  /**
   * Save settings to localStorage
   */
  _saveSettings() {
    // Persist to localStorage - this is the source of truth for settings
    const key = this._settingsKey || 'shopping_list_settings_default';
    localStorage.setItem(key, JSON.stringify(this._settings));
  }

  set hass(hass) {
    const oldHass = this._hass;
    this._hass = hass;
    
    // Load data when hass is first set
    if (!oldHass && hass) {
      this._loadData();
      this._startPolling();
    }
  }

  setConfig(config) {
    this._config = { ...config };  // shallow-copy: HA 2026+ freezes the original
    // Derive a unique settings key for THIS card instance so each card on
    // the dashboard keeps its own independent settings in localStorage.
    // Set `card_id` in YAML for an explicit stable label; otherwise title is used.
    const id = (config.card_id || config.title || 'shopping_list').toString().trim().toLowerCase().replace(/[^a-z0-9_]/g, '_');
    this._settingsKey = `shopping_list_settings_${id}`;
    // Re-load settings now that we have the correct key
    this._settings = this._loadSettings();
  }

  /**
   * Load data using Home Assistant's connection.sendMessagePromise
   */
  /**
   * Compare two objects for actual data changes (ignoring order and timestamps)
   */
  _hasDataChanged(oldData, newData) {
    if (!oldData && !newData) return false;
    if (!oldData || !newData) return true;
    
    const oldKeys = Object.keys(oldData).sort();
    const newKeys = Object.keys(newData).sort();
    
    // Different number of items = changed
    if (oldKeys.length !== newKeys.length) return true;
    
    // Check if keys are different
    if (JSON.stringify(oldKeys) !== JSON.stringify(newKeys)) return true;
    
    // Check if values are different (only compare qty, name, category)
    for (const key of oldKeys) {
      const oldItem = oldData[key];
      const newItem = newData[key];
      
      // For active list, only compare qty
      if (oldItem.qty !== undefined && newItem.qty !== undefined) {
        if (oldItem.qty !== newItem.qty) return true;
      }
      // For products, compare name, category, and image
      else {
        if (oldItem.name !== newItem.name || oldItem.category !== newItem.category || oldItem.image !== newItem.image) {
          return true;
        }
      }
    }
    
    return false;
  }

  async _loadData() {
    if (!this._hass || !this._hass.connection) {
      return;
    }
    
    try {
      const [products, activeList] = await Promise.all([
        this._hass.connection.sendMessagePromise({
          type: 'shopping_list_manager/get_products'
        }),
        this._hass.connection.sendMessagePromise({
          type: 'shopping_list_manager/get_active'
        })
      ]);
      
      // Check if data actually changed before re-rendering
      const productsChanged = this._hasDataChanged(this._products, products || {});
      const activeChanged = this._hasDataChanged(this._activeList, activeList || {});
      const isFirstLoad = this._isLoading;
      
      
      this._products = products || {};
      this._activeList = activeList || {};
      this._isLoading = false;
      
      // Render on first load or if data changed
      if (isFirstLoad || productsChanged || activeChanged) {
        // On first load, do full render. On updates, just update content
        if (isFirstLoad) {
          this._render();
        } else {
          this._updateContent();
        }
      } else {
      }
    } catch (error) {
      console.error('Failed to load shopping list data:', error);
      this._isLoading = false;
      // Only update content on error, don't rebuild entire UI
      if (this.shadowRoot.querySelector('.card-content')) {
        this._updateContent();
      } else {
        this._render();
      }
    }
  }

  /**
   * Poll for updates every 10 seconds (only when page is visible)
   */
  _startPolling() {
    if (!this._hass || this._pollInterval) {
      return;
    }
    
    this._pollInterval = setInterval(() => {
      // Only poll if page is visible and user isn't actively typing
      if (this._hass && this._hass.connection && !document.hidden) {
        this._loadData();
      }
    }, 3000); // 3 seconds
    
    // Also poll when page becomes visible again
    this._visibilityHandler = () => {
      if (!document.hidden && this._hass && this._hass.connection) {
        this._loadData();
      }
    };
    document.addEventListener('visibilitychange', this._visibilityHandler);
  }

  /**
   * Fetch and cache the directory listing from the shopping_list_manager image folder.
   * HA's static file server returns an HTML page with <a> links for each file.
   */
  async _fetchImageList() {
    if (this._imageListCache !== null) return this._imageListCache;

    const dir = '/local/images/shopping_list_manager/';
    try {
      const res = await fetch(dir);
      if (!res.ok) {
        console.warn('[ShoppingList] Image directory fetch returned', res.status, '— falling back to direct-guess mode');
        this._imageListCache = [];
        return [];
      }
      const html = await res.text();
      console.log('[ShoppingList] Raw directory HTML length:', html.length);

      // Extract href values from <a> tags
      const matches = [...html.matchAll(/href="([^"]+)"/g)];
      const imageExts = /\.(png|jpg|jpeg|gif|svg|webp)$/i;

      this._imageListCache = matches
        .map(m => {
          // Normalise: strip any leading path so we keep just the filename
          // e.g. "/local/images/shopping_list_manager/milk.png" → "milk.png"
          let h = m[1];
          const lastSlash = h.lastIndexOf('/');
          if (lastSlash !== -1) h = h.substring(lastSlash + 1);
          return h;
        })
        .filter(h => imageExts.test(h));

      console.log('[ShoppingList] Parsed image list (' + this._imageListCache.length + ' files):', this._imageListCache);
    } catch (e) {
      console.warn('[ShoppingList] Could not fetch image list:', e, '— falling back to direct-guess mode');
      this._imageListCache = [];
    }
    return this._imageListCache;
  }

  /**
   * Score a single filename against the product name.
   * Returns 0-100.  Higher = better match.
   *
   * Strategy (order of priority):
   *   100  – exact stem match            "Milk" vs "milk.png"
   *    80  – stem starts-with product    "Milk" vs "milk_whole.png"
   *    70  – product starts-with stem    "Whole milk" vs "milk.png"  (rare but possible)
   *    50  – product contains stem       "Semi skimmed milk" vs "milk.png"
   *    40  – stem contains product       "milk_chocolate" vs "milk" — product is a substring
   *    20  – any shared token (word)     "organic_milk" vs "milk_2litre"
   *     0  – no overlap
   */
  _scoreImage(productName, filename) {
    // Strip extension and path, normalise
    const stem = filename.replace(/\.[^.]+$/, '').toLowerCase().replace(/[-]/g, '_');
    const prod = productName.toLowerCase().trim().replace(/[\s-]+/g, '_');

    if (stem === prod)                          return 100;
    if (stem.startsWith(prod))                  return 80;
    if (prod.startsWith(stem))                  return 70;
    if (prod.includes(stem))                    return 50;
    if (stem.includes(prod))                    return 40;

    // Token-level overlap
    const stemTokens = new Set(stem.split('_').filter(Boolean));
    const prodTokens = new Set(prod.split('_').filter(Boolean));
    for (const t of prodTokens) {
      if (stemTokens.has(t)) return 20;
    }
    return 0;
  }

  /**
   * Find the best-matching local image for a product name.
   * Fetches the directory listing once, then scores every file.
   * Results are cached per product name for the session.
   */
  /**
   * Try to load a single URL; resolves true/false within 2 s.
   */
  _testImageUrl(url) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload  = () => resolve(true);
      img.onerror = () => resolve(false);
      img.src = url;
      setTimeout(() => resolve(false), 2000);
    });
  }

  /**
   * Direct-guess fallback: try the product name (and common
   * singular/plural tweaks) with every extension directly.
   * Returns the first URL that loads, or null.
   */
  async _guessImageDirect(productName) {
    const dir  = '/local/images/shopping_list_manager/';
    const base = productName.toLowerCase().trim().replace(/[\s-]+/g, '_');
    const exts = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'];

    // Build candidate stems: exact, +s, -s, -es, -ies→y
    const stems = [base];
    if (!base.endsWith('s'))              stems.push(base + 's');        // carrot  → carrots
    if (base.endsWith('s'))               stems.push(base.slice(0,-1));  // carrots → carrot
    if (base.endsWith('es'))              stems.push(base.slice(0,-2));  // tomatoes → tomat  (covered by -s too)
    if (base.endsWith('ies'))             stems.push(base.slice(0,-3) + 'y'); // berries → berry

    for (const stem of stems) {
      for (const ext of exts) {
        const url = `${dir}${stem}.${ext}`;
        if (await this._testImageUrl(url)) {
          console.log('[ShoppingList] Direct-guess hit:', url);
          return url;
        }
      }
    }
    return null;
  }

  async _findLocalImage(productName) {
    const cacheKey = productName.toLowerCase().trim();
    if (this._localImageCache[cacheKey] !== undefined) {
      return this._localImageCache[cacheKey];
    }

    const dir  = '/local/images/shopping_list_manager/';
    const files = await this._fetchImageList();

    let bestScore = 0;
    let bestFile  = null;

    // --- Pass 1: score against the directory listing (if we got one) ---
    if (files.length > 0) {
      for (const file of files) {
        const score = this._scoreImage(productName, file);
        if (score > bestScore) {
          bestScore = score;
          bestFile  = file;
          if (score === 100) break;
        }
      }
      console.log('[ShoppingList] Best listing match for "' + productName + '":', bestFile, 'score=' + bestScore);
    }

    // Accept listing match if score >= 20
    if (bestScore >= 20 && bestFile) {
      const result = `${dir}${bestFile}`;
      this._localImageCache[cacheKey] = result;
      return result;
    }

    // --- Pass 2: direct HTTP guess (works even when listing is empty/404) ---
    console.log('[ShoppingList] Listing empty or no match — trying direct guess for "' + productName + '"');
    const guessed = await this._guessImageDirect(productName);
    this._localImageCache[cacheKey] = guessed;
    return guessed;
  }

  /**
   * Search for appropriate emoji based on product name
   */
  _searchEmoji(productName) {
    const name = productName.toLowerCase().trim();
    
    // Common food and grocery emojis mapped to keywords
    const emojiMap = {
      // Fruits
      'apple': '🍎', 'banana': '🍌', 'orange': '🍊', 'lemon': '🍋', 'lime': '🍋',
      'watermelon': '🍉', 'grapes': '🍇', 'grape': '🍇', 'strawberry': '🍓', 'strawberries': '🍓',
      'melon': '🍈', 'cherry': '🍒', 'cherries': '🍒', 'peach': '🍑', 'pear': '🍐',
      'pineapple': '🍍', 'kiwi': '🥝', 'avocado': '🥑', 'mango': '🥭', 'coconut': '🥥',
      
      // Vegetables
      'tomato': '🍅', 'tomatoes': '🍅', 'cucumber': '🥒', 'carrot': '🥕', 'carrots': '🥕',
      'potato': '🥔', 'potatoes': '🥔', 'corn': '🌽', 'pepper': '🫑', 'peppers': '🫑',
      'broccoli': '🥦', 'lettuce': '🥬', 'salad': '🥗', 'onion': '🧅', 'onions': '🧅',
      'garlic': '🧄', 'mushroom': '🍄', 'mushrooms': '🍄', 'eggplant': '🍆', 'aubergine': '🍆',
      
      // Meat & Protein
      'meat': '🥩', 'beef': '🥩', 'steak': '🥩', 'chicken': '🍗', 'poultry': '🍗',
      'bacon': '🥓', 'pork': '🥓', 'ham': '🍖', 'sausage': '🌭', 'egg': '🥚', 'eggs': '🥚',
      'fish': '🐟', 'salmon': '🐟', 'tuna': '🐟', 'shrimp': '🦐', 'prawn': '🦐',
      
      // Dairy
      'milk': '🥛', 'cheese': '🧀', 'butter': '🧈', 'yogurt': '🥛', 'yoghurt': '🥛',
      'cream': '🥛', 'ice cream': '🍦', 'icecream': '🍦',
      
      // Bakery
      'bread': '🍞', 'baguette': '🥖', 'croissant': '🥐', 'bagel': '🥯', 'pretzel': '🥨',
      'roll': '🥖', 'rolls': '🥖', 'bun': '🍔', 'buns': '🍔', 'cake': '🎂', 'cookie': '🍪',
      'cookies': '🍪', 'donut': '🍩', 'doughnut': '🍩', 'pie': '🥧', 'muffin': '🧁',
      
      // Pantry
      'pasta': '🍝', 'spaghetti': '🍝', 'rice': '🍚', 'noodles': '🍜', 'ramen': '🍜',
      'pizza': '🍕', 'burger': '🍔', 'sandwich': '🥪', 'taco': '🌮', 'burrito': '🌯',
      'soup': '🍲', 'stew': '🍲', 'can': '🥫', 'canned': '🥫', 'jar': '🫙',
      
      // Snacks & Sweets
      'chocolate': '🍫', 'candy': '🍬', 'lollipop': '🍭', 'chips': '🍟', 'crisps': '🍟',
      'popcorn': '🍿', 'nuts': '🥜', 'peanut': '🥜', 'honey': '🍯',
      
      // Drinks
      'coffee': '☕', 'tea': '🍵', 'beer': '🍺', 'wine': '🍷', 'champagne': '🍾',
      'juice': '🧃', 'soda': '🥤', 'water': '💧', 'bottle': '🍾',
      
      // Condiments
      'salt': '🧂', 'pepper': '🫑', 'oil': '🫒', 'vinegar': '🫗', 'sauce': '🥫',
      'ketchup': '🍅', 'mustard': '🌭', 'mayo': '🥚', 'mayonnaise': '🥚',
      
      // Household
      'toilet': '🧻', 'paper': '🧻', 'soap': '🧼', 'shampoo': '🧴', 'detergent': '🧴',
      'cleaning': '🧹', 'bleach': '🧴', 'sponge': '🧽', 'trash': '🗑️', 'bin': '🗑️',
      
      // Baby
      'baby': '👶', 'diaper': '🍼', 'nappy': '🍼', 'formula': '🍼', 'wipes': '🧻',
      
      // Pet
      'dog': '🐕', 'cat': '🐈', 'pet': '🐾', 'food': '🐾'
    };
    
    // Try exact match first
    if (emojiMap[name]) {
      return emojiMap[name];
    }
    
    // Try partial matches (check if any keyword is in the product name)
    for (const [keyword, emoji] of Object.entries(emojiMap)) {
      if (name.includes(keyword)) {
        return emoji;
      }
    }
    
    // Default fallback
    return '🛒';
  }

  /**
   * Add a new product - opens the unified dialog in "new" mode
   */
  async _addNewProduct(name) {
    const key = this._generateKey(name);
    
    if (this._products[key]) {
      alert('Product already exists');
      return;
    }
    
    // Auto-search: try local image first, then fall back to emoji
    const localImage = await this._findLocalImage(name);
    const autoImage = localImage || this._searchEmoji(name);
    
    // Open the same dialog used for editing, but in "new" mode
    const result = await this._showEditDialog(null, { name, image: autoImage });
    
    // Always clear search after dialog closes (cancel or save)
    this._searchQuery = '';
    const _sb = this.shadowRoot.querySelector('.search-bar');
    if (_sb) _sb.value = '';
    const _sc = this.shadowRoot.querySelector('.search-clear');
    if (_sc) _sc.style.display = 'none';
    const _addBtn = this.shadowRoot.querySelector('.settings-btn');
    if (_addBtn) { _addBtn.textContent = '⚙️'; _addBtn.title = 'Settings'; }
    this._updateContent();
    
    if (!result || result.action !== 'save') return;
    
    try {
      await this._hass.connection.sendMessagePromise({
        type: 'shopping_list_manager/add_product',
        key: key,
        name: result.name,
        category: result.category,
        unit: 'pcs',
        image: result.image || ''
      });
      
      await this._hass.connection.sendMessagePromise({
        type: 'shopping_list_manager/set_qty',
        key: key,
        qty: 1
      });
      
      await this._loadData();
      this._hapticFeedback();
    } catch (error) {
      console.error('Failed to add product:', error);
      alert('Failed to add product: ' + error.message);
    }
  }
  
  /**
   * Show product edit dialog
   */
  async _showEditDialog(productKey, newProductDefaults = null) {
    // "new" mode when productKey is null and defaults are passed
    const isNew = !productKey && newProductDefaults;
    const product = isNew
      ? { name: newProductDefaults.name || '', image: newProductDefaults.image || '', category: 'other' }
      : this._products[productKey];
    if (!product) return;
    
    return new Promise((resolve) => {
      const modal = document.createElement('div');
      modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0,0,0,0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 100000;
        isolation: isolate;
      `;
      
      const dialog = document.createElement('div');
      dialog.style.cssText = `
        background: var(--card-background-color);
        border-radius: 12px;
        padding: 24px;
        max-width: 400px;
        width: 90%;
      `;
      
      const currentCategory = CATEGORY_MAP[product.category] || CATEGORY_MAP['other'];
      
      dialog.innerHTML = `
        <h2 style="margin: 0 0 16px 0; color: var(--primary-text-color);">
          ${isNew ? 'New Product' : 'Edit Product'}
        </h2>
        
        <div style="margin-bottom: 16px;">
          <label style="display: block; margin-bottom: 8px; color: var(--primary-text-color); font-weight: 500;">
            Product Name
          </label>
          <input type="text" class="edit-name" value="${product.name}" style="
            width: 100%;
            padding: 12px;
            border: 1px solid var(--divider-color);
            border-radius: 8px;
            background: var(--card-background-color);
            color: var(--primary-text-color);
            font-size: 16px;
          "/>
        </div>
        
        <div style="margin-bottom: 16px;">
          <label style="display: block; margin-bottom: 8px; color: var(--primary-text-color); font-weight: 500;">
            Image / Emoji
          </label>
          <input type="text" class="edit-image" value="${product.image || ''}" placeholder="URL or emoji (e.g., 🍎)" style="
            width: 100%;
            padding: 12px;
            border: 1px solid var(--divider-color);
            border-radius: 8px;
            background: var(--card-background-color);
            color: var(--primary-text-color);
            font-size: 16px;
          "/>
          <div style="font-size: 11px; color: var(--secondary-text-color); margin-top: 4px;">
            Enter URL (http://...) or emoji. Leave empty for 🛒
          </div>
        </div>
        
        <div style="margin-bottom: 16px;">
          <label style="display: block; margin-bottom: 8px; color: var(--primary-text-color); font-weight: 500;">
            Category
          </label>
          <select class="edit-category" style="
            width: 100%;
            padding: 10px 12px;
            border: 1px solid var(--divider-color);
            border-radius: 8px;
            background: var(--card-background-color);
            color: var(--primary-text-color);
            font-size: 15px;
            cursor: pointer;
            appearance: auto;
          ">
            ${CATEGORIES.map(cat => `<option value="${cat.id}" ${cat.id === product.category ? 'selected' : ''}>${cat.emoji} ${cat.name}</option>`).join('')}
          </select>
        </div>
        
        <div style="display: flex; gap: 8px;">
          ${isNew ? '' : `<button class="delete-btn" style="
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: #f44336;
            color: white;
            cursor: pointer;
            font-weight: 500;
          ">Delete</button>`}
          
          <button class="cancel-btn" style="
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: var(--divider-color);
            color: var(--primary-text-color);
            cursor: pointer;
          ">Cancel</button>
          
          <button class="save-btn" style="
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: var(--primary-color);
            color: var(--text-primary-color);
            cursor: pointer;
            font-weight: 500;
          ">${isNew ? 'Add' : 'Save'}</button>
        </div>
      `;
      
      modal.appendChild(dialog);
      document.body.appendChild(modal);
      
      // Save button
      dialog.querySelector('.save-btn').addEventListener('click', () => {
        const newName    = dialog.querySelector('.edit-name').value.trim();
        const newImage   = dialog.querySelector('.edit-image').value.trim();
        const newCategory = dialog.querySelector('.edit-category').value;
        if (!newName) {
          alert('Product name cannot be empty');
          return;
        }
        document.body.removeChild(modal);
        resolve({ action: 'save', name: newName, category: newCategory, image: newImage });
      });
      
      // Delete button (only present in edit mode)
      const deleteBtn = dialog.querySelector('.delete-btn');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', () => {
          if (confirm(`Delete "${product.name}"?`)) {
            document.body.removeChild(modal);
            resolve({ action: 'delete' });
          }
        });
      }
      
      // Cancel button
      dialog.querySelector('.cancel-btn').addEventListener('click', () => {
        document.body.removeChild(modal);
        resolve(null);
      });
      
      // Backdrop click
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          document.body.removeChild(modal);
          resolve(null);
        }
      });
    });
  }
  
  /**
   * Edit a product
   */
  async _editProduct(productKey) {
    const result = await this._showEditDialog(productKey);
    if (!result) return;
    
    try {
      if (result.action === 'delete') {
        // Delete product
        await this._hass.connection.sendMessagePromise({
          type: 'shopping_list_manager/delete_product',
          key: productKey
        });
        
        // Reload data
        await this._loadData();
        this._hapticFeedback();
      } else if (result.action === 'save') {
        // Update product
        await this._hass.connection.sendMessagePromise({
          type: 'shopping_list_manager/add_product',
          key: productKey,
          name: result.name,
          category: result.category,
          unit: 'pcs',
          image: result.image || ''
        });
        
        // Reload data
        await this._loadData();
        this._hapticFeedback();
      }
    } catch (error) {
      console.error('Failed to edit product:', error);
      alert('Failed to edit product: ' + error.message);
    }
  }

  /**
   * Set quantity for a product
   */
  async _setQuantity(productKey, qty) {
    const currentQty = this._activeList[productKey]?.qty || 0;
    
    // Optimistic update
    if (qty === 0) {
      delete this._activeList[productKey];
    } else {
      this._activeList[productKey] = { qty };
    }
    this._render();
    this._hapticFeedback();
    
    try {
      await this._hass.connection.sendMessagePromise({
        type: 'shopping_list_manager/set_qty',
        key: productKey,
        qty: qty
      });
    } catch (error) {
      console.error('Failed to set quantity:', error);
      // Revert on error
      if (currentQty === 0) {
        delete this._activeList[productKey];
      } else {
        this._activeList[productKey] = { qty: currentQty };
      }
      this._render();
      alert('Failed to update quantity');
    }
  }

  /**
   * Toggle product on/off list
   */
  async _toggleProduct(productKey) {
    const currentQty = this._activeList[productKey]?.qty || 0;
    const newQty = currentQty > 0 ? 0 : 1;
    await this._setQuantity(productKey, newQty);
  }

  /**
   * Increment quantity
   */
  async _incrementProduct(productKey) {
    const currentQty = this._activeList[productKey]?.qty || 0;
    await this._setQuantity(productKey, currentQty + 1);
  }

  /**
   * Decrement quantity
   */
  async _decrementProduct(productKey) {
    const currentQty = this._activeList[productKey]?.qty || 0;
    if (currentQty > 0) {
      await this._setQuantity(productKey, currentQty - 1);
    }
  }

  /**
   * Generate product key from name
   */
  _generateKey(name) {
    return name.toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '');
  }

  /**
   * Haptic feedback based on settings
   */
  _hapticFeedback(intensity = 'medium') {
    if (this._settings.haptics === 'off') return;
    
    if ('vibrate' in navigator) {
      const patterns = {
        low: 5,
        medium: 10,
        high: 20
      };
      
      const duration = patterns[this._settings.haptics] || patterns.medium;
      navigator.vibrate(duration);
    }
  }

  /**
   * Show settings modal
   */
  _showSettings() {
    return new Promise((resolve) => {
      const modal = document.createElement('div');
      modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0,0,0,0.5);
        display: flex;
        align-items: flex-end;
        justify-content: center;
        z-index: 100000;
        isolation: isolate;
      `;
      
      const dialog = document.createElement('div');
      dialog.style.cssText = `
        background: var(--card-background-color);
        border-radius: 16px 16px 0 0;
        padding: 12px 24px 32px 24px;
        width: 100%;
        max-width: 480px;
        max-height: 70vh;
        overflow-y: auto;
        position: relative;
      `;
      
      dialog.innerHTML = `
        <!-- drag handle pill -->
        <div style="width: 36px; height: 4px; background: var(--divider-color); border-radius: 2px; margin: 0 auto 16px auto;"></div>
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">
          <h2 style="margin: 0; color: var(--primary-text-color); font-size: 18px;">Settings</h2>
          <button class="close-x-btn" style="background: none; border: none; color: var(--primary-text-color); font-size: 20px; cursor: pointer; padding: 4px 8px; border-radius: 6px; line-height: 1;">✕</button>
        </div>
        
        <!-- Haptics Setting -->
        <div style="margin-bottom: 24px;">
          <label style="display: block; margin-bottom: 8px; color: var(--primary-text-color); font-weight: 500;">
            Haptic Feedback
          </label>
          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">
            ${['off', 'low', 'medium', 'high'].map(level => `
              <button class="haptic-btn" data-level="${level}" style="
                padding: 12px 8px;
                border: 2px solid ${this._settings.haptics === level ? 'var(--primary-color)' : 'var(--divider-color)'};
                border-radius: 8px;
                background: ${this._settings.haptics === level ? 'var(--primary-color)' : 'var(--card-background-color)'};
                color: var(--primary-text-color);
                cursor: pointer;
                font-size: 12px;
                text-transform: capitalize;
              ">${level}</button>
            `).join('')}
          </div>
        </div>
        
        <!-- Products Per Row -->
        <div style="margin-bottom: 24px;">
          <label style="display: block; margin-bottom: 8px; color: var(--primary-text-color); font-weight: 500;">
            Products Per Row
          </label>
          <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px;">
            ${['auto', '2', '3', '4', '5'].map(count => `
              <button class="perrow-btn" data-count="${count}" style="
                padding: 12px 8px;
                border: 2px solid ${this._settings.productsPerRow === count ? 'var(--primary-color)' : 'var(--divider-color)'};
                border-radius: 8px;
                background: ${this._settings.productsPerRow === count ? 'var(--primary-color)' : 'var(--card-background-color)'};
                color: var(--primary-text-color);
                cursor: pointer;
                font-size: 12px;
                text-transform: capitalize;
              ">${count}</button>
            `).join('')}
          </div>
        </div>
        
        <!-- Layout Setting -->
        <div style="margin-bottom: 24px;">
          <label style="display: block; margin-bottom: 8px; color: var(--primary-text-color); font-weight: 500;">
            Layout
          </label>
          <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;">
            <button class="layout-btn" data-layout="grid" style="
              padding: 16px;
              border: 2px solid ${this._settings.layout === 'grid' ? 'var(--primary-color)' : 'var(--divider-color)'};
              border-radius: 8px;
              background: ${this._settings.layout === 'grid' ? 'var(--primary-color)' : 'var(--card-background-color)'};
              color: var(--primary-text-color);
              cursor: pointer;
              display: flex;
              flex-direction: column;
              align-items: center;
              gap: 8px;
            ">
              <span style="font-size: 24px;">▦</span>
              <span style="font-size: 12px;">Grid</span>
            </button>
            <button class="layout-btn" data-layout="list" style="
              padding: 16px;
              border: 2px solid ${this._settings.layout === 'list' ? 'var(--primary-color)' : 'var(--divider-color)'};
              border-radius: 8px;
              background: ${this._settings.layout === 'list' ? 'var(--primary-color)' : 'var(--card-background-color)'};
              color: var(--primary-text-color);
              cursor: pointer;
              display: flex;
              flex-direction: column;
              align-items: center;
              gap: 8px;
            ">
              <span style="font-size: 24px;">☰</span>
              <span style="font-size: 12px;">List</span>
            </button>
          </div>
        </div>
        
        <!-- Hide Completed Toggle -->
        <div style="margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; padding: 12px; border-radius: 8px; background: var(--card-background-color); border: 1px solid var(--divider-color);">
          <div>
            <div style="font-weight: 500; color: var(--primary-text-color); margin-bottom: 4px;">Hide Completed</div>
            <div style="font-size: 12px; color: var(--secondary-text-color);">Hide products with quantity 0</div>
          </div>
          <label style="position: relative; display: inline-block; width: 44px; height: 24px; margin: 0;">
            <input type="checkbox" class="hide-completed-toggle" ${this._settings.hideCompleted ? 'checked' : ''} style="opacity: 0; width: 0; height: 0;">
            <span style="position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: ${this._settings.hideCompleted ? 'var(--primary-color)' : 'var(--divider-color)'}; transition: .4s; border-radius: 24px;"></span>
            <span style="position: absolute; height: 18px; width: 18px; left: ${this._settings.hideCompleted ? '23px' : '3px'}; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%;"></span>
          </label>
        </div>
        
        <!-- Compact Headers Toggle -->
        <div style="margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; padding: 12px; border-radius: 8px; background: var(--card-background-color); border: 1px solid var(--divider-color);">
          <div>
            <div style="font-weight: 500; color: var(--primary-text-color); margin-bottom: 4px;">Compact Headers</div>
            <div style="font-size: 12px; color: var(--secondary-text-color);">Show category names only (no emoji)</div>
          </div>
          <label style="position: relative; display: inline-block; width: 44px; height: 24px; margin: 0;">
            <input type="checkbox" class="compact-headers-toggle" ${this._settings.compactHeaders ? 'checked' : ''} style="opacity: 0; width: 0; height: 0;">
            <span style="position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: ${this._settings.compactHeaders ? 'var(--primary-color)' : 'var(--divider-color)'}; transition: .4s; border-radius: 24px;"></span>
            <span style="position: absolute; height: 18px; width: 18px; left: ${this._settings.compactHeaders ? '23px' : '3px'}; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%;"></span>
          </label>
        </div>

        <button class="close-btn" style="
          width: 100%;
          padding: 12px;
          border: none;
          border-radius: 8px;
          background: var(--primary-color);
          color: var(--text-primary-color);
          cursor: pointer;
          font-size: 16px;
        ">Done</button>
      `;
      
      modal.appendChild(dialog);
      document.body.appendChild(modal);
      
      // Haptics buttons
      dialog.querySelectorAll('.haptic-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          this._settings.haptics = btn.dataset.level;
          this._saveSettings();
          
          // Update visual selection
          dialog.querySelectorAll('.haptic-btn').forEach(b => {
            b.style.borderColor = 'var(--divider-color)';
            b.style.background = 'var(--card-background-color)';
          });
          btn.style.borderColor = 'var(--primary-color)';
          btn.style.background = 'var(--primary-color)';
          
          // Test vibration
          this._hapticFeedback();
        });
      });
      
      // Products per row buttons
      dialog.querySelectorAll('.perrow-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          this._settings.productsPerRow = btn.dataset.count;
          this._saveSettings();
          this._updateContent(); // apply grid change immediately
          
          // Update visual selection
          dialog.querySelectorAll('.perrow-btn').forEach(b => {
            b.style.borderColor = 'var(--divider-color)';
            b.style.background = 'var(--card-background-color)';
          });
          btn.style.borderColor = 'var(--primary-color)';
          btn.style.background = 'var(--primary-color)';
          
          this._hapticFeedback();
        });
      });
      
      // Hide completed toggle
      const hideCompletedToggle = dialog.querySelector('.hide-completed-toggle');
      if (hideCompletedToggle) {
        hideCompletedToggle.addEventListener('change', (e) => {
          this._settings.hideCompleted = e.target.checked;
          this._saveSettings();
          
          // Update toggle visual state
          const toggle = e.target.parentElement;
          const slider = toggle.querySelectorAll('span')[0];
          const knob = toggle.querySelectorAll('span')[1];
          slider.style.backgroundColor = e.target.checked ? 'var(--primary-color)' : 'var(--divider-color)';
          knob.style.left = e.target.checked ? '23px' : '3px';
          
          this._updateContent();
          this._hapticFeedback();
        });
      }

      // Compact headers toggle
      const compactHeadersToggle = dialog.querySelector('.compact-headers-toggle');
      if (compactHeadersToggle) {
        compactHeadersToggle.addEventListener('change', (e) => {
          this._settings.compactHeaders = e.target.checked;
          this._saveSettings();
          
          // Update toggle visual state
          const toggle = e.target.parentElement;
          const slider = toggle.querySelectorAll('span')[0];
          const knob = toggle.querySelectorAll('span')[1];
          slider.style.backgroundColor = e.target.checked ? 'var(--primary-color)' : 'var(--divider-color)';
          knob.style.left = e.target.checked ? '23px' : '3px';
          
          this._updateContent();
          this._hapticFeedback();
        });
      }
      
      // Layout buttons
      dialog.querySelectorAll('.layout-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          this._settings.layout = btn.dataset.layout;
          this._saveSettings();
          this._updateContent(); // switch grid↔list immediately
          
          // Update visual selection
          dialog.querySelectorAll('.layout-btn').forEach(b => {
            b.style.borderColor = 'var(--divider-color)';
            b.style.background = 'var(--card-background-color)';
          });
          btn.style.borderColor = 'var(--primary-color)';
          btn.style.background = 'var(--primary-color)';
          
          this._hapticFeedback();
        });
      });
      
      // Close button (Done)
      dialog.querySelector('.close-btn').addEventListener('click', () => {
        document.body.removeChild(modal);
        this._updateContent();
        resolve();
      });

      // ✕ top-right close button
      dialog.querySelector('.close-x-btn').addEventListener('click', () => {
        document.body.removeChild(modal);
        this._updateContent();
        resolve();
      });
      
      // Backdrop click
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          document.body.removeChild(modal);
          this._updateContent();
          resolve();
        }
      });
    });
  }

  /**
   * Fuzzy search - matches even with typos or partial matches
   */
  _fuzzyMatch(text, query) {
    text = text.toLowerCase();
    query = query.toLowerCase();
    
    // Exact match or substring
    if (text.includes(query)) {
      return true;
    }
    
    // Fuzzy match - allows for missing characters
    let queryIndex = 0;
    for (let i = 0; i < text.length && queryIndex < query.length; i++) {
      if (text[i] === query[queryIndex]) {
        queryIndex++;
      }
    }
    return queryIndex === query.length;
  }

  /**
   * Filter products by search and split into active/inactive
   */
  _getFilteredProducts() {
    let products = Object.values(this._products);
    
    // Filter by search query with fuzzy matching
    if (this._searchQuery) {
      const query = this._searchQuery.toLowerCase();
      products = products.filter(product =>
        this._fuzzyMatch(product.name, query)
      );
    }
    
    // Filter by selected category
    if (this._selectedCategory) {
      products = products.filter(product => 
        product.category === this._selectedCategory
      );
    }
    
    // Sort products
    if (this._sortBy === 'category') {
      // Sort by category order, then by name
      products.sort((a, b) => {
        const catA = CATEGORY_MAP[a.category] || CATEGORY_MAP['other'];
        const catB = CATEGORY_MAP[b.category] || CATEGORY_MAP['other'];
        
        if (catA.order !== catB.order) {
          return catA.order - catB.order;
        }
        return a.name.localeCompare(b.name);
      });
    } else {
      // Alphabetical sort
      products.sort((a, b) => a.name.localeCompare(b.name));
    }
    
    return products;
  }
  
  /**
   * Get active products (in shopping list)
   */
  _getActiveProducts() {
    const filtered = this._getFilteredProducts();
    return filtered.filter(product => {
      const qty = this._activeList[product.key]?.qty || 0;
      return qty > 0;
    });
  }
  
  /**
   * Get inactive products (not in shopping list)
   */
  _getInactiveProducts() {
    const filtered = this._getFilteredProducts();
    return filtered.filter(product => {
      const qty = this._activeList[product.key]?.qty || 0;
      return qty === 0;
    });
  }
  
  /**
   * Check if should show "Add New" button
   */
  _shouldShowAddNew() {
    if (!this._searchQuery || this._searchQuery.length < 2) {
      return false;
    }
    
    const query = this._searchQuery.toLowerCase();
    const exactMatch = Object.values(this._products).some(
      product => product.name.toLowerCase() === query
    );
    
    return !exactMatch;
  }

  /**
   * Render the card
   */
  _render() {
    // Only do initial render if the structure doesn't exist
    if (!this.shadowRoot.querySelector('.card-content')) {
      this._initialRender();
      return;
    }
    
    // Otherwise just update the content area
    this._updateContent();
  }
  
  /**
   * Initial render - creates the persistent structure
   */
  _initialRender() {
    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          padding: 0px;
          overflow: hidden;
        }
        
        .card-content {
          max-width: 100%;
          overflow: hidden;
        }
        
        .search-container {
          display: flex;
          gap: 8px;
          margin-bottom: 12px;
          align-items: center;
          width: 100%;
        }
        
        .search-wrapper {
          position: relative;
          flex: 1;
          min-width: 0;
        }
        
        .search-bar {
          width: 100%;
          padding: 12px 40px 12px 12px;
          font-size: 16px;
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          box-sizing: border-box;
        }
        
        .search-clear {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          color: var(--secondary-text-color);
          cursor: pointer;
          font-size: 20px;
          padding: 4px 8px;
          display: none;
        }
        
        .search-clear.visible {
          display: block;
        }
        
        .settings-btn {
          width: 44px;
          min-width: 44px;
          height: 44px;
          flex-shrink: 0;
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        
        .controls {
          display: flex;
          gap: 8px;
          margin-bottom: 16px;
          flex-wrap: wrap;
        }
        
        .control-btn {
          padding: 8px 16px;
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 14px;
        }
        
        .control-btn.active {
          background: var(--primary-color);
          color: var(--text-primary-color);
          border-color: var(--primary-color);
        }
        

        
        .category-section {
          margin-bottom: 24px;
        }
        
        .category-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
          padding: 8px 0;
          border-bottom: 2px solid var(--divider-color);
        }
        
        .category-header.compact {
          padding: 4px 0;
          margin-bottom: 8px;
          border-bottom: 1px solid var(--divider-color);
        }
        
        .category-emoji {
          font-size: 24px;
        }
        
        .category-name {
          font-size: 16px;
          font-weight: bold;
          color: var(--primary-text-color);
        }
        
        .category-header.compact .category-name {
          font-size: 14px;
          font-weight: 500;
        }
        
        .product-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
          gap: 6px;
          width: 100%;
          max-width: 100%;
        }
        
        .product-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        
        .product-tile {
          background: rgba(var(--rgb-secondary-text-color, 128, 128, 128), 0.08);
          border: 1px solid rgba(var(--rgb-divider-color, 128, 128, 128), 0.15);
          border-radius: 12px;
          cursor: pointer;
          user-select: none;
          transition: all 0.15s ease;
          box-sizing: border-box;
          overflow: hidden;
          position: relative;
          container-type: inline-size;
        }
        
        .product-grid .product-tile {
          aspect-ratio: 1;
          min-height: 0;
          max-width: 100%;
          padding: 8px;
        }
        
        .product-list .product-tile {
          flex-direction: row;
          padding: 16px;
          aspect-ratio: unset;
        }
        
        .product-tile.active {
          background: var(--primary-color);
          border-color: var(--primary-color);
          border-width: 1px;
        }
        
        .product-tile.active .product-name {
          color: white;
          font-weight: 600;
        }
        
        .product-tile.active .qty-button {
          background: rgba(255, 255, 255, 0.25);
          border-color: rgba(255, 255, 255, 0.4);
          color: white;
        }
        
        .product-tile.active .qty-button.plus-btn {
          background: rgba(255, 255, 255, 0.95);
          color: var(--primary-color);
          border-color: rgba(255, 255, 255, 0.95);
        }
        
        .product-tile:active {
          transform: scale(0.95);
        }
        
        /* ── Name: single line at top ── */
        .product-name {
          font-size: 12px;
          text-align: center;
          font-weight: 500;
          color: var(--primary-text-color);
          line-height: 1.2;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          padding: 0 5px;
          position: absolute;
          top: 5px;
          left: 0;
          right: 0;
          z-index: 1;
        }
        @container (min-width: 150px) {
          .product-name { font-size: 14px; top: 6px; }
        }
        @container (min-width: 220px) {
          .product-name { font-size: 15px; top: 8px; }
        }

        /* ── Icon box: everything between name and button row ── */
        .product-icon-container {
          position: absolute;
          top: 20px;
          left: 5px;
          right: 5px;
          bottom: 26px;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
        }
        @container (min-width: 150px) {
          .product-icon-container { top: 24px; bottom: 30px; }
        }
        @container (min-width: 220px) {
          .product-icon-container { top: 28px; bottom: 34px; }
        }

        /* ── Emoji: font-size scales with tile width via container queries ── */
        .product-emoji {
          font-size: clamp(24px, 65cqw, 220px);
          line-height: 1;
          user-select: none;
        }

        /* ── Image: contained, never stretches ── */
        .product-image {
          max-width: 120%;
          max-height: 120%;
          width: auto;
          height: auto;
          object-fit: contain;
          user-select: none;
          pointer-events: none;
        }

        /* ── Tap-to-add badge ── */
        .tap-to-add {
          position: absolute;
          bottom: 5px;
          left: 50%;
          transform: translateX(-50%);
          color: var(--secondary-text-color);
          font-size: 10px;
          opacity: 0.7;
          background: rgba(var(--rgb-card-background-color, 30, 30, 30), 0.85);
          padding: 1px 5px;
          border-radius: 4px;
          white-space: nowrap;
          z-index: 1;
        }
        @container (min-width: 150px) {
          .tap-to-add { font-size: 11px; bottom: 6px; }
        }

        .product-secondary {
          font-size: 10px;
          color: var(--secondary-text-color);
          opacity: 0.8;
        }

        /* ── list-layout overrides ── */
        .product-list .product-name {
          position: relative;
          flex: 1;
          text-align: left;
          top: auto; left: auto; right: auto;
          white-space: nowrap;
          font-size: 14px;
        }

        /* ── Quantity controls row: pinned to bottom corners ── */
        .quantity-controls {
          position: absolute;
          bottom: 3px;
          left: 3px;
          right: 3px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          pointer-events: none;
          z-index: 1;
        }
        @container (min-width: 150px) {
          .quantity-controls { bottom: 4px; left: 4px; right: 4px; }
        }

        .product-list .quantity-controls {
          position: relative;
          width: auto;
          gap: 8px;
          bottom: auto; left: auto; right: auto;
          pointer-events: auto;
        }

        /* ── Buttons ── */
        .qty-button {
          width: 24px;
          height: 24px;
          border-radius: 50%;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 13px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          pointer-events: auto;
          position: relative;
        }
        @container (min-width: 150px) {
          .qty-button { width: 28px; height: 28px; font-size: 14px; }
        }
        @container (min-width: 220px) {
          .qty-button { width: 32px; height: 32px; font-size: 15px; }
        }

        /* Larger hit area for easier clicking on mobile */
        .qty-button::before {
          content: '';
          position: absolute;
          top: -8px;
          left: -8px;
          right: -8px;
          bottom: -8px;
          border-radius: 50%;
        }
        
        .qty-button.plus-btn {
          background: var(--primary-color);
          color: white;
          border-color: var(--primary-color);
          font-weight: bold;
        }
        
        .qty-button:active {
          background: var(--divider-color);
        }
        
        
        .empty-state {
          text-align: center;
          padding: 32px;
          color: var(--secondary-text-color);
        }
      </style>
      
      <ha-card header="${(this._config && this._config.title) || 'Shopping List'}">
        <div class="card-content">
          <div class="search-container">
            <div class="search-wrapper">
              <input
                type="text"
                class="search-bar"
                placeholder="Search products..."
                value="${this._searchQuery}"
              />
              <button class="search-clear" style="position: absolute !important; right: 8px !important; top: 50% !important; transform: translateY(-50%) !important; background: var(--divider-color) !important; border: none !important; color: var(--primary-text-color) !important; cursor: pointer !important; font-size: 16px !important; padding: 4px 8px !important; border-radius: 4px !important; display: ${this._searchQuery ? 'block' : 'none'} !important; z-index: 10 !important;">✕</button>
            </div>
            <button class="settings-btn" title="Settings" style="width: 44px !important; min-width: 44px !important; height: 44px !important; border: 1px solid var(--divider-color) !important; background: var(--card-background-color) !important; color: var(--primary-text-color) !important; cursor: pointer !important; font-size: 20px !important; display: flex !important; align-items: center !important; justify-content: center !important; flex-shrink: 0 !important; border-radius: 8px !important;">⚙️</button>
          </div>
          
          <div class="controls">
            <button class="control-btn ${this._sortBy === 'category' ? 'active' : ''}" data-sort="category">
              By Category
            </button>
            <button class="control-btn ${this._sortBy === 'alphabet' ? 'active' : ''}" data-sort="alphabet">
              A-Z
            </button>
          </div>
          
          <div class="content-area"></div>
        </div>
      </ha-card>
    `;
    
    this._attachPersistentListeners();
    this._updateContent();
  }
  
  /**
   * Update only the content area (not search bar)
   */
  _updateContent() {
    const contentArea = this.shadowRoot.querySelector('.content-area');
    if (!contentArea) return;
    
    if (this._isLoading) {
      contentArea.innerHTML = '<div style="padding: 16px; text-align: center;">Loading...</div>';
      return;
    }
    
    const activeProducts = this._getActiveProducts();
    const inactiveProducts = this._getInactiveProducts();
    let html = '';
    

    
    // Show active products first
    if (activeProducts.length > 0) {
      if (this._sortBy === 'category') {
        html += this._renderProductsByCategory(activeProducts, false);
      } else {
        const containerClass = this._settings.layout === 'list' ? 'product-list' : 'product-grid';
        html += `<div class="${containerClass}">`;
        html += activeProducts.map(product => this._renderProductTile(product)).join('');
        html += '</div>';
      }
    }
    
    // Show inactive products in "Recently Used" section (unless hidden)
    if (inactiveProducts.length > 0 && !this._searchQuery && !this._settings.hideCompleted) {
      html += `
        <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--divider-color);">
          <div style="font-size: 12px; color: var(--secondary-text-color); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500;">
            Recently Used
          </div>
          ${this._sortBy === 'category' ? 
            this._renderProductsByCategory(inactiveProducts, true) : 
            `<div class="${this._settings.layout === 'list' ? 'product-list' : 'product-grid'}">
              ${inactiveProducts.map(product => this._renderProductTile(product)).join('')}
            </div>`
          }
        </div>
      `;
    }
    
    // Empty state
    if (activeProducts.length === 0 && inactiveProducts.length === 0) {
      html += `
        <div class="empty-state">
          ${this._searchQuery ? 'No products found' : 'No products yet. Search to add your first product!'}
        </div>
      `;
    }
    
    contentArea.innerHTML = html;

    // Stamp live grid columns onto every .product-grid so the setting
    // takes effect immediately without needing a full re-render.
    const gridCols = this._settings.productsPerRow === 'auto'
      ? 'repeat(auto-fill, minmax(120px, 1fr))'
      : `repeat(${this._settings.productsPerRow}, 1fr)`;
    contentArea.querySelectorAll('.product-grid').forEach(g => {
      g.style.gridTemplateColumns = gridCols;
    });

    this._attachContentListeners();
  }
  
  /**
   * Render products by category (helper for active/inactive)
   */
  _renderProductsByCategory(products, isRecentlyUsed) {
    const containerClass = this._settings.layout === 'list' ? 'product-list' : 'product-grid';
    const productsByCategory = {};
    
    products.forEach(product => {
      const categoryId = product.category || 'other';
      if (!productsByCategory[categoryId]) {
        productsByCategory[categoryId] = [];
      }
      productsByCategory[categoryId].push(product);
    });
    
    return CATEGORIES
      .filter(cat => productsByCategory[cat.id] && productsByCategory[cat.id].length > 0)
      .map(cat => {
        const categoryProducts = productsByCategory[cat.id];
        const headerHtml = this._settings.compactHeaders 
          ? `<div class="category-header compact"><span class="category-name">${cat.name}</span></div>`
          : `<div class="category-header"><span class="category-emoji">${cat.emoji}</span><span class="category-name">${cat.name}</span></div>`;
        return `
          <div class="category-section">
            ${headerHtml}
            <div class="${containerClass}">
              ${categoryProducts.map(product => this._renderProductTile(product)).join('')}
            </div>
          </div>
        `;
      }).join('');
  }
  
  /**
   * Attach listeners that persist (search bar, sort buttons)
   */
  _attachPersistentListeners() {
    const searchBar = this.shadowRoot.querySelector('.search-bar');
    const searchClear = this.shadowRoot.querySelector('.search-clear');
    const settingsBtn = this.shadowRoot.querySelector('.settings-btn');
    
    if (searchBar) {
      searchBar.addEventListener('input', (e) => {
        this._searchQuery = e.target.value;
        // ✕ clear button: show/hide based on text
        if (searchClear) {
          searchClear.style.display = this._searchQuery.length > 0 ? 'block' : 'none';
        }
        // Settings/Add button: swap ⚙️ ↔ ➕ based on whether "add new" applies
        if (settingsBtn) {
          if (this._searchQuery.length > 0 && this._shouldShowAddNew()) {
            settingsBtn.textContent = '➕';
            settingsBtn.title = 'Add new product';
          } else {
            settingsBtn.textContent = '⚙️';
            settingsBtn.title = 'Settings';
          }
        }
        this._updateContent();
      });
    }
    
    // ✕ clear search
    if (searchClear) {
      searchClear.addEventListener('click', () => {
        this._searchQuery = '';
        searchBar.value = '';
        searchClear.style.display = 'none';
        if (settingsBtn) { settingsBtn.textContent = '⚙️'; settingsBtn.title = 'Settings'; }
        searchBar.focus();
        this._updateContent();
        this._hapticFeedback();
      });
    }
    
    // Settings / Add button (toggles based on search state)
    if (settingsBtn) {
      settingsBtn.addEventListener('click', () => {
        if (settingsBtn.textContent === '➕') {
          this._addNewProduct(this._searchQuery);
        } else {
          this._showSettings();
        }
        this._hapticFeedback();
      });
    }
    
    const sortButtons = this.shadowRoot.querySelectorAll('.control-btn[data-sort]');
    sortButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        this._sortBy = btn.dataset.sort;
        // Update button states
        sortButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._updateContent();
        this._hapticFeedback();
      });
    });
  }
  
  /**
   * Attach listeners for content area (products, buttons)
   */
  _attachContentListeners() {
    // Product tiles - add long-press for edit
    const tiles = this.shadowRoot.querySelectorAll('.product-tile');
    tiles.forEach(tile => {
      const key = tile.dataset.key;
      let longPressTimer = null;
      let longPressTriggered = false;
      
      // Touch events for mobile long-press
      tile.addEventListener('touchstart', (e) => {
        longPressTriggered = false;
        longPressTimer = setTimeout(() => {
          longPressTriggered = true;
          this._hapticFeedback();
          this._editProduct(key);
        }, 500); // 500ms long press
      }, { passive: true });
      
      tile.addEventListener('touchend', () => {
        if (longPressTimer) {
          clearTimeout(longPressTimer);
        }
      });
      
      tile.addEventListener('touchmove', () => {
        if (longPressTimer) {
          clearTimeout(longPressTimer);
        }
      }, { passive: true });
      
      // Mouse events for desktop
      tile.addEventListener('mousedown', (e) => {
        longPressTriggered = false;
        longPressTimer = setTimeout(() => {
          longPressTriggered = true;
          this._editProduct(key);
        }, 500);
      });
      
      tile.addEventListener('mouseup', () => {
        if (longPressTimer) {
          clearTimeout(longPressTimer);
        }
      });
      
      tile.addEventListener('mouseleave', () => {
        if (longPressTimer) {
          clearTimeout(longPressTimer);
        }
      });
      
      // Right-click for edit
      tile.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        this._editProduct(key);
      });
      
      // Regular click
      tile.addEventListener('click', (e) => {
        // Don't toggle if it was a long press or clicking buttons
        if (!longPressTriggered && !e.target.closest('.qty-button')) {
          // Check if click is in bottom 30px area (where buttons would be)
          const rect = tile.getBoundingClientRect();
          const clickY = e.clientY - rect.top;
          const isBottomArea = clickY > (rect.height - 35);
          
          // Only toggle if not clicking in button area
          if (!isBottomArea || !isActive) {
            this._toggleProduct(key);
          }
        }
      });
    });
    
    // Plus buttons
    const plusButtons = this.shadowRoot.querySelectorAll('.plus-btn');
    plusButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._incrementProduct(btn.dataset.key);
      });
    });
    
    // Minus buttons
    const minusButtons = this.shadowRoot.querySelectorAll('.minus-btn');
    minusButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._decrementProduct(btn.dataset.key);
      });
    });
  }
  
  /**
   * Render a single product tile
   */
  _renderProductTile(product) {
    const qty = this._activeList[product.key]?.qty || 0;
    const isActive = qty > 0;
    const hasImage = product.image && product.image.trim().length > 0;
    
    // Determine if image is URL or emoji
    const isUrl = hasImage && (product.image.startsWith('http') || product.image.startsWith('/'));
    const displayImage = hasImage ? product.image : '🛒';
    
    return `
      <div class="product-tile ${isActive ? 'active' : ''}" data-key="${product.key}">
        <div class="product-name">${product.name}</div>
        
        <div class="product-icon-container">
          ${isUrl ? 
            `<img src="${displayImage}" class="product-image" alt="${product.name}" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
             <div class="product-emoji" style="display: none;">🛒</div>` :
            `<div class="product-emoji">${displayImage}</div>`
          }
        </div>
        
        ${isActive ? `
          <div class="quantity-controls">
            <button class="qty-button minus-btn" data-key="${product.key}">−</button>
            <button class="qty-button plus-btn" data-key="${product.key}">${qty}</button>
          </div>
        ` : `
          <div class="tap-to-add">Tap to add</div>
        `}
      </div>
    `;
  }

  disconnectedCallback() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
    }
    if (this._visibilityHandler) {
      document.removeEventListener('visibilitychange', this._visibilityHandler);
    }
  }

  // Temporarily disabled GUI editor - use YAML configuration
  // static getConfigElement() {
  //   return document.createElement('shopping-list-card-editor');
  // }

  static getStubConfig() {
    return { title: 'Shopping List' };
  }

  getCardSize() {
    return 3;
  }
}

// ── GUI Config Editor ─────────────────────────────────────────
// This is the standard HA card-editor pattern.  HA renders this
// element inside its "configure card" panel automatically when the
// card exposes a static getConfigElement() method.
class ShoppingListCardEditor extends HTMLElement {
  setConfig(config) {
    console.log('[Editor] setConfig called, _rendered:', this._rendered, 'config:', config);
    this._config = { ...(config || {}) };  // shallow-copy: HA 2026+ freezes the original
    if (!this._rendered) {
      console.log('[Editor] First render, calling _render()');
      this._render();   // only render once, then STOP
    } else {
      console.log('[Editor] Already rendered, ignoring setConfig');
    }
    // After first render, ignore setConfig calls - the updateConfig closure
    // already handles live updates by mutating this._config directly
  }

  set hass(hass) {
    console.log('[Editor] hass setter called, _rendered:', this._rendered);
    this._hass = hass;
    if (!this._rendered) this._render();
  }

  _render() {
    if (!this._config) return;  // nothing to render yet

    // Attach shadow DOM once, reuse on subsequent renders
    if (!this.shadowRoot) {
      this.attachShadow({ mode: 'open' });
    }

    const title           = this._config.title            || '';
    const productsPerRow  = String(this._config.products_per_row || '3');
    const layout          = this._config.layout           || 'grid';
    const haptics         = this._config.haptics          || 'medium';
    const hideCompleted   = !!this._config.hide_completed;
    const compactHeaders  = !!this._config.compact_headers;

    this.shadowRoot.innerHTML = `
      <style>
        .row {
          display: flex;
          gap: 8px;
          margin-bottom: 16px;
          flex-wrap: wrap;
        }
        ha-text-field, ha-select {
          display: block;
          flex: 1;
          min-width: 200px;
        }
        .toggle-row {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          padding: 12px 0;
          gap: 12px;
        }
        .toggle-row + .toggle-row {
          border-top: 1px solid var(--divider-color);
        }
        .toggle-text {
          display: flex;
          flex-direction: column;
          flex: 1;
          min-width: 0;
        }
        .toggle-label {
          font-size: 14px;
          color: var(--primary-text-color);
          font-weight: 400;
        }
        .toggle-hint {
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-top: 2px;
        }
        .section-divider {
          border: none;
          border-top: 1px solid var(--divider-color);
          margin: 8px 0 16px 0;
        }
        .code-editor-link {
          display: block;
          margin-top: 16px;
          padding: 12px 0 0 0;
          border-top: 1px solid var(--divider-color);
          font-size: 14px;
          color: var(--primary-color);
          cursor: pointer;
          background: none;
          border-left: none;
          border-right: none;
          border-bottom: none;
          text-align: left;
          width: 100%;
        }
        .code-editor-link:hover { text-decoration: underline; }
        .yaml-block {
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          padding: 12px;
          margin-top: 8px;
          font-family: monospace;
          font-size: 13px;
          color: var(--primary-text-color);
          white-space: pre;
          overflow-x: auto;
          max-height: 200px;
          overflow-y: auto;
        }
      </style>

      <!-- Title -->
      <div class="row">
        <ha-text-field id="ed-title" label="Title" placeholder="Shopping List"></ha-text-field>
      </div>

      <!-- Products Per Row -->
      <div class="row">
        <ha-select id="ed-perrow" label="Products Per Row">
          <mwc-list-item value="auto">Auto</mwc-list-item>
          <mwc-list-item value="2">2</mwc-list-item>
          <mwc-list-item value="3">3</mwc-list-item>
          <mwc-list-item value="4">4</mwc-list-item>
          <mwc-list-item value="5">5</mwc-list-item>
        </ha-select>

        <!-- Layout -->
        <ha-select id="ed-layout" label="Layout">
          <mwc-list-item value="grid">Grid</mwc-list-item>
          <mwc-list-item value="list">List</mwc-list-item>
        </ha-select>
      </div>

      <!-- Haptic Feedback -->
      <div class="row">
        <ha-select id="ed-haptics" label="Haptic Feedback">
          <mwc-list-item value="off">Off</mwc-list-item>
          <mwc-list-item value="low">Low</mwc-list-item>
          <mwc-list-item value="medium">Medium</mwc-list-item>
          <mwc-list-item value="high">High</mwc-list-item>
        </ha-select>
      </div>

      <hr class="section-divider">

      <!-- Toggle: Hide completed items -->
      <div class="toggle-row">
        <div class="toggle-text">
          <span class="toggle-label">Hide completed items</span>
          <span class="toggle-hint">Hides the "Recently Used" section showing products not currently on the list.</span>
        </div>
        <ha-switch id="ed-hide-completed"></ha-switch>
      </div>

      <!-- Toggle: Compact headers -->
      <div class="toggle-row">
        <div class="toggle-text">
          <span class="toggle-label">Compact headers</span>
          <span class="toggle-hint">Show category names only (no emoji)</span>
        </div>
        <ha-switch id="ed-hide-headers"></ha-switch>
      </div>

      <!-- Show/hide YAML preview -->
      <button class="code-editor-link" id="ed-code-toggle">
        ${this._showCodeEditor ? 'Hide code editor' : 'Show code editor'}
      </button>
      ${this._showCodeEditor ? `<div class="yaml-block">${this._toYaml()}</div>` : ''}
    `;

    // ── Set values imperatively (reliable with shadow DOM + HA components) ──
    const titleEl          = this.shadowRoot.querySelector('#ed-title');
    const perrowEl         = this.shadowRoot.querySelector('#ed-perrow');
    const layoutEl         = this.shadowRoot.querySelector('#ed-layout');
    const hapticsEl        = this.shadowRoot.querySelector('#ed-haptics');
    const hideCompletedEl  = this.shadowRoot.querySelector('#ed-hide-completed');
    const hideHeadersEl    = this.shadowRoot.querySelector('#ed-hide-headers');

    titleEl.value          = title;
    perrowEl.value         = productsPerRow;
    layoutEl.value         = layout;
    hapticsEl.value        = haptics;
    hideCompletedEl.checked = hideCompleted;
    hideHeadersEl.checked  = compactHeaders;

    // ── Single updateConfig closure — mirrors your working pattern ──
    const updateConfig = () => {
      console.log('[Editor] updateConfig called');
      this._config = {
        ...this._config,
        title:                titleEl.value || 'Shopping List',
        products_per_row:     perrowEl.value,
        layout:               layoutEl.value,
        haptics:              hapticsEl.value,
        hide_completed:   hideCompletedEl.checked,
        compact_headers:  hideHeadersEl.checked
      };
      console.log('[Editor] Dispatching config-changed:', this._config);
      this.dispatchEvent(new CustomEvent('config-changed', {
        detail: { config: this._config },
        bubbles: true,
        composed: true
      }));
    };

    titleEl.addEventListener('input', updateConfig);
    perrowEl.addEventListener('value-changed', updateConfig);
    layoutEl.addEventListener('value-changed', updateConfig);
    hapticsEl.addEventListener('value-changed', updateConfig);
    hideCompletedEl.addEventListener('checked-changed', updateConfig);
    hideHeadersEl.addEventListener('checked-changed', updateConfig);

    this.shadowRoot.querySelector('#ed-code-toggle').addEventListener('click', () => {
      this._showCodeEditor = !this._showCodeEditor;
      this._render();
    });

    this._rendered = true;
  }

  _toYaml() {
    const lines = ['type: custom:shopping-list-card'];
    if (this._config.title)                lines.push('title: ' + this._config.title);
    if (this._config.products_per_row)     lines.push('products_per_row: ' + this._config.products_per_row);
    if (this._config.layout)               lines.push('layout: ' + this._config.layout);
    if (this._config.haptics)          lines.push('haptics: ' + this._config.haptics);
    if (this._config.hide_completed)   lines.push('hide_completed: true');
    if (this._config.compact_headers)  lines.push('compact_headers: true');
    return lines.join('\n');
  }
}

customElements.define('shopping-list-card-editor', ShoppingListCardEditor);
customElements.define('shopping-list-card', ShoppingListCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'shopping-list-card',
  name: 'Shopping List Card',
  description: 'A shopping list card with search, categories, and product images.',
  preview: false
});
