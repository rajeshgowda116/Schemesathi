with open('chatbot.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Enhanced initializeSchemeFromUrl
old_init = '''    function initializeSchemeFromUrl() {
      const params = new URLSearchParams(window.location.search);
      const schemeParam = params.get('scheme');
      const idParam = params.get('id');

      // Match scheme
      if (idParam) {
        currentScheme = ALL_SCHEMES.find(s => String(s.id) === String(idParam));
      }
      if (!currentScheme && schemeParam) {
        const norm = schemeParam.toLowerCase().trim();
        currentScheme = ALL_SCHEMES.find(s => s.scheme_name.toLowerCase().includes(norm) || norm.includes(s.scheme_name.toLowerCase()));
      }

      // Fallback: Default to Gruha Lakshmi Scheme if no param specified
      if (!currentScheme) {
        currentScheme = ALL_SCHEMES.find(s => s.scheme_name.includes('Gruha Lakshmi')) || ALL_SCHEMES[0];
      }

      setupSchemeChatUI();
      loadSchemeHistory();
    }'''

new_init = '''    function initializeSchemeFromUrl() {
      const params = new URLSearchParams(window.location.search);
      const schemeParam = params.get('scheme');
      const idParam = params.get('id');

      // Match scheme by ID first
      if (idParam) {
        currentScheme = ALL_SCHEMES.find(s => String(s.id) === String(idParam) || String(s.scheme_id) === String(idParam));
      }
      
      // Match scheme by name or keywords
      if (!currentScheme && schemeParam) {
        const norm = schemeParam.toLowerCase().trim();
        currentScheme = ALL_SCHEMES.find(s => s.scheme_name.toLowerCase().includes(norm) || norm.includes(s.scheme_name.toLowerCase()));
        if (!currentScheme) {
          const words = norm.split(/\\s+/).filter(w => w.length > 2 && w !== 'scheme');
          currentScheme = ALL_SCHEMES.find(s => words.some(w => s.scheme_name.toLowerCase().includes(w)));
        }
        // If not in preloaded catalog, synthesize dedicated custom scheme object
        if (!currentScheme) {
          const capitalizedName = schemeParam.trim().split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
          currentScheme = {
            id: null,
            scheme_id: null,
            scheme_name: capitalizedName.includes('Scheme') ? capitalizedName : capitalizedName + ' Scheme',
            department: 'Government of Karnataka',
            description: `Official citizen welfare program: ${capitalizedName}.`,
            benefits: ['Direct citizen assistance as notified by the Government of Karnataka.'],
            eligibility: ['Karnataka state resident citizens as per scheme guidelines.'],
            documents_required: ['Aadhaar Card', 'Residential Proof', 'Income/Caste Certificate (if applicable)'],
            official_url: 'https://sevasindhugs1.karnataka.gov.in/'
          };
        }
      }

      // Fallback: Default to Gruha Lakshmi Scheme if no param specified
      if (!currentScheme) {
        currentScheme = ALL_SCHEMES.find(s => s.scheme_name.includes('Gruha Lakshmi')) || ALL_SCHEMES[0];
      }

      setupSchemeChatUI();
      loadSchemeHistory();
    }'''

content = content.replace(old_init, new_init)

# Enhanced isAskingAboutDifferentScheme
old_guardrail = '''    // Check if the query is attempting to ask about a DIFFERENT scheme
    function isAskingAboutDifferentScheme(query) {
      const q = query.toLowerCase();
      const currentNameNorm = currentScheme.scheme_name.toLowerCase();

      // Check against all other schemes in our catalog
      for (const other of ALL_SCHEMES) {
        if (other.id === currentScheme.id) continue;

        const otherName = other.scheme_name.toLowerCase();
        // Check for distinctive keywords of other schemes
        const distinctiveKeywords = [];
        if (otherName.includes('scholarship') || otherName.includes('post-matric')) distinctiveKeywords.push('post-matric', 'ssp scholarship', 'post matric');
        if (otherName.includes('yuva nidhi')) distinctiveKeywords.push('yuva nidhi');
        if (otherName.includes('gruha lakshmi')) distinctiveKeywords.push('gruha lakshmi', 'lakshmi scheme');
        if (otherName.includes('gruha jyoti')) distinctiveKeywords.push('gruha jyoti', 'free electricity', '200 units');
        if (otherName.includes('shakti')) distinctiveKeywords.push('shakti scheme', 'free bus travel');
        if (otherName.includes('anna bhagya')) distinctiveKeywords.push('anna bhagya', 'free rice');
        if (otherName.includes('vidya nidhi')) distinctiveKeywords.push('farmer vidya nidhi', 'raitha vidya');
        if (otherName.includes('ganga kalyana')) distinctiveKeywords.push('ganga kalyana', 'borewell');
        if (otherName.includes('cmegp')) distinctiveKeywords.push('cmegp');
        if (otherName.includes('arivu')) distinctiveKeywords.push('arivu loan', 'arivu education loan');

        for (const kw of distinctiveKeywords) {
          if (q.includes(kw) && !currentNameNorm.includes(kw)) {
            return other.scheme_name;
          }
        }
      }

      // Generic other scheme queries
      if (q.includes('other schemes') || q.includes('all schemes') || q.includes('different scheme') || q.includes('what other programs')) {
        return 'Other Schemes';
      }

      return null;
    }'''

new_guardrail = '''    // Check if the query is attempting to ask about a DIFFERENT scheme
    function isAskingAboutDifferentScheme(query) {
      const q = query.toLowerCase();
      const currentNameNorm = currentScheme.scheme_name.toLowerCase();

      // Check against all other schemes in our catalog
      for (const other of ALL_SCHEMES) {
        if (other.id && currentScheme.id && other.id === currentScheme.id) continue;
        if (other.scheme_name.toLowerCase() === currentNameNorm) continue;

        const otherName = other.scheme_name.toLowerCase();
        // Check for distinctive keywords of other schemes
        const distinctiveKeywords = [];
        if (otherName.includes('scholarship') || otherName.includes('post-matric')) distinctiveKeywords.push('post-matric', 'ssp scholarship', 'post matric', 'pre-matric');
        if (otherName.includes('yuva nidhi')) distinctiveKeywords.push('yuva nidhi', 'yuvanidhi', 'unemployment allowance', 'unemployed graduate');
        if (otherName.includes('gruha lakshmi')) distinctiveKeywords.push('gruha lakshmi', 'gruhalakshmi', 'lakshmi scheme', '2000 rupees', '2000 dbt', 'woman head dbt');
        if (otherName.includes('gruha jyoti')) distinctiveKeywords.push('gruha jyoti', 'gruhajyoti', 'free electricity', '200 units', 'power bill', 'free power');
        if (otherName.includes('shakti')) distinctiveKeywords.push('shakti scheme', 'shakti', 'free bus travel', 'free bus', 'uchita prayana', 'ksrtc free');
        if (otherName.includes('anna bhagya')) distinctiveKeywords.push('anna bhagya', 'annabhagya', 'free rice', '10 kg rice', 'dbt rice');
        if (otherName.includes('vidya nidhi')) distinctiveKeywords.push('farmer vidya nidhi', 'raitha vidya', 'vidya nidhi');
        if (otherName.includes('ganga kalyana')) distinctiveKeywords.push('ganga kalyana', 'gangakalyana', 'borewell', 'irrigation pump');
        if (otherName.includes('cmegp')) distinctiveKeywords.push('cmegp', 'chief minister employment', 'micro enterprise');
        if (otherName.includes('arivu')) distinctiveKeywords.push('arivu loan', 'arivu education loan', 'arivu');

        for (const kw of distinctiveKeywords) {
          if (q.includes(kw) && !currentNameNorm.includes(kw)) {
            return other.scheme_name;
          }
        }
      }

      // Generic other scheme queries
      const genericOtherPatterns = [
        'other scheme', 'other schemes', 'all schemes', 'different scheme', 'different schemes', 
        'what other programs', 'list of schemes', 'another scheme', 'tell me about other', 'any other'
      ];
      if (genericOtherPatterns.some(pattern => q.includes(pattern))) {
        return 'Other Karnataka Schemes';
      }

      return null;
    }'''

content = content.replace(old_guardrail, new_guardrail)

with open('chatbot.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("chatbot.html updated successfully!")
