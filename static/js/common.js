// Authentication and User Management
function isAuthenticated() {
    return localStorage.getItem('user') !== null;
}

function getCurrentUser() {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
}

function logout() {
    localStorage.removeItem('user');
    router.navigate('/login');
}

// Theme Management
function initializeTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    
    // Update theme toggle icon
    const themeIcon = document.querySelector('#themeToggle i');
    if (themeIcon) {
        themeIcon.className = theme === 'dark' ? 'ri-moon-line' : 'ri-sun-line';
    }
}

function toggleTheme() {
    const currentTheme = localStorage.getItem('theme') || 'light';
    setTheme(currentTheme === 'light' ? 'dark' : 'light');
}

// Show/Hide Navigation based on auth state
function updateNavVisibility() {
    const nav = document.querySelector('.main-nav');
    const isLoggedIn = isAuthenticated();
    
    if (nav) {
        nav.style.display = isLoggedIn ? 'flex' : 'none';
    }
}

// Toast notification system
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="ri-${type === 'success' ? 'check-line' : type === 'error' ? 'error-warning-line' : 'information-line'}"></i>
        <span>${message}</span>
    `;

    const container = document.getElementById('toast-container');
    container.appendChild(toast);

    // Remove toast after 3 seconds
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Format currency values
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0
    }).format(amount);
}

// Form validation utilities
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function validatePassword(password) {
    // At least 8 characters, 1 letter, and 1 number
    const re = /^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$/;
    return re.test(password);
}

// Form handling utilities
function handleFormSubmit(form, callback) {
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Disable submit button to prevent double submission
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
        }

        try {
            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());
            await callback(data);
        } catch (error) {
            showToast(error.message || 'An error occurred', 'error');
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
            }
        }
    });
}

// Input validation and formatting
function setupInputValidation(input, validationFn, errorMsg) {
    input.addEventListener('input', () => {
        const isValid = validationFn(input.value);
        input.setCustomValidity(isValid ? '' : errorMsg);
        
        // Update visual feedback
        input.classList.toggle('is-invalid', !isValid);
        input.classList.toggle('is-valid', isValid);
        
        // Update error message display
        const feedbackDiv = input.parentElement.querySelector('.invalid-feedback');
        if (feedbackDiv) {
            feedbackDiv.textContent = isValid ? '' : errorMsg;
        }
    });
}

// Number input formatting
function formatNumberInput(input) {
    input.addEventListener('input', () => {
        let value = input.value.replace(/[^\d]/g, '');
        if (value) {
            value = parseInt(value, 10).toLocaleString('en-IN');
            input.value = value;
        }
    });
}

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    initializeTheme();
    updateNavVisibility();
});

// Export common functions
window.isAuthenticated = isAuthenticated;
window.getCurrentUser = getCurrentUser;
window.logout = logout;
window.toggleTheme = toggleTheme;
window.formatCurrency = formatCurrency;
window.validateEmail = validateEmail;
window.validatePassword = validatePassword;
window.handleFormSubmit = handleFormSubmit;
window.setupInputValidation = setupInputValidation;
window.formatNumberInput = formatNumberInput;
