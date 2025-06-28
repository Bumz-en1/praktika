// Theme Management
function initTheme() {
    const savedTheme = localStorage.getItem("theme") || "light"
    document.documentElement.setAttribute("data-theme", savedTheme)
    updateThemeIcon(savedTheme)
  }
  
  function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute("data-theme")
    const newTheme = currentTheme === "dark" ? "light" : "dark"
  
    document.documentElement.setAttribute("data-theme", newTheme)
    localStorage.setItem("theme", newTheme)
    updateThemeIcon(newTheme)
  }
  
  function updateThemeIcon(theme) {
    const icon = document.getElementById("theme-icon")
    if (icon) {
      icon.textContent = theme === "dark" ? "☀️" : "🌙"
    }
  }
  
  // Notifications
  function showNotification(message, type = "success") {
    const notification = document.createElement("div")
    notification.className = `notification ${type}`
    notification.textContent = message
  
    // Add notification styles
    notification.style.cssText = `
          position: fixed;
          top: 20px;
          right: 20px;
          padding: 1rem 1.5rem;
          border-radius: 8px;
          color: white;
          font-weight: 500;
          z-index: 1000;
          transform: translateX(400px);
          transition: transform 0.3s ease;
          max-width: 300px;
      `
  
    // Set background color based on type
    switch (type) {
      case "success":
        notification.style.backgroundColor = "#27ae60"
        break
      case "error":
        notification.style.backgroundColor = "#e74c3c"
        break
      case "warning":
        notification.style.backgroundColor = "#f39c12"
        break
      default:
        notification.style.backgroundColor = "#3498db"
    }
  
    document.body.appendChild(notification)
  
    // Show notification
    setTimeout(() => {
      notification.style.transform = "translateX(0)"
    }, 100)
  
    // Hide notification
    setTimeout(() => {
      notification.style.transform = "translateX(400px)"
      setTimeout(() => {
        if (document.body.contains(notification)) {
          document.body.removeChild(notification)
        }
      }, 300)
    }, 4000)
  }
  
  // Form Validation
  function validateForm(form) {
    const requiredFields = form.querySelectorAll("[required]")
    let isValid = true
  
    requiredFields.forEach((field) => {
      if (!field.value.trim()) {
        field.style.borderColor = "#e74c3c"
        isValid = false
      } else {
        field.style.borderColor = ""
      }
    })
  
    return isValid
  }
  
  // File Upload Handling
  function setupFileUpload() {
    const fileInputs = document.querySelectorAll('input[type="file"]')
  
    fileInputs.forEach((input) => {
      input.addEventListener("change", (e) => {
        const file = e.target.files[0]
        if (file) {
          // Validate file size (50MB max)
          if (file.size > 50 * 1024 * 1024) {
            showNotification("Файл слишком большой. Максимальный размер: 50MB", "error")
            e.target.value = ""
            return
          }
  
          // Show file name
          const fileName = file.name
          showNotification(`Файл выбран: ${fileName}`, "success")
        }
      })
    })
  }
  
  // Drag and Drop
  function setupDragAndDrop() {
    const dropZones = document.querySelectorAll(".file-upload-area")
  
    dropZones.forEach((zone) => {
      const fileInput = zone.querySelector('input[type="file"]')
  
      zone.addEventListener("dragover", (e) => {
        e.preventDefault()
        zone.classList.add("drag-over")
      })
  
      zone.addEventListener("dragleave", (e) => {
        e.preventDefault()
        zone.classList.remove("drag-over")
      })
  
      zone.addEventListener("drop", (e) => {
        e.preventDefault()
        zone.classList.remove("drag-over")
  
        const files = e.dataTransfer.files
        if (files.length > 0 && fileInput) {
          fileInput.files = files
  
          // Trigger change event
          const event = new Event("change", { bubbles: true })
          fileInput.dispatchEvent(event)
        }
      })
    })
  }
  
  // URL Parameters
  function getUrlParameter(name) {
    const urlParams = new URLSearchParams(window.location.search)
    return urlParams.get(name)
  }
  
  // Handle URL notifications
  function handleUrlNotifications() {
    const success = getUrlParameter("success")
    const error = getUrlParameter("error")
    const message = getUrlParameter("message")
  
    if (success) {
      let successMessage = "Операция выполнена успешно!"
      if (success === "edit") successMessage = "Данные успешно обновлены!"
      if (success === "delete") successMessage = "Запись успешно удалена!"
      showNotification(successMessage, "success")
    }
  
    if (error) {
      showNotification(decodeURIComponent(error), "error")
    }
  
    if (message) {
      showNotification(decodeURIComponent(message), "info")
    }
  }
  
  // Form Submission with Loading
  function setupFormSubmission() {
    const forms = document.querySelectorAll("form")
  
    forms.forEach((form) => {
      form.addEventListener("submit", (e) => {
        const submitBtn = form.querySelector('button[type="submit"]')
  
        if (submitBtn) {
          const originalText = submitBtn.textContent
          submitBtn.textContent = "Загрузка..."
          submitBtn.disabled = true
  
          // Re-enable after 30 seconds (fallback)
          setTimeout(() => {
            submitBtn.textContent = originalText
            submitBtn.disabled = false
          }, 30000)
        }
      })
    })
  }
  
  // Password Strength Indicator
  function setupPasswordStrength() {
    const passwordInputs = document.querySelectorAll('input[type="password"]')
  
    passwordInputs.forEach((input) => {
      if (input.name === "password" || input.name === "new_password") {
        input.addEventListener("input", () => {
          const strength = calculatePasswordStrength(input.value)
          showPasswordStrength(input, strength)
        })
      }
    })
  }
  
  function calculatePasswordStrength(password) {
    let score = 0
  
    if (password.length >= 8) score++
    if (/[a-z]/.test(password)) score++
    if (/[A-Z]/.test(password)) score++
    if (/[0-9]/.test(password)) score++
    if (/[^A-Za-z0-9]/.test(password)) score++
  
    return score
  }
  
  function showPasswordStrength(input, strength) {
    let indicator = input.parentNode.querySelector(".password-strength")
  
    if (!indicator) {
      indicator = document.createElement("div")
      indicator.className = "password-strength"
      indicator.style.cssText = `
              margin-top: 0.5rem;
              font-size: 0.875rem;
              font-weight: 500;
          `
      input.parentNode.appendChild(indicator)
    }
  
    const levels = ["Очень слабый", "Слабый", "Средний", "Хороший", "Отличный"]
    const colors = ["#e74c3c", "#e67e22", "#f39c12", "#27ae60", "#2ecc71"]
  
    if (strength > 0) {
      indicator.textContent = `Надежность: ${levels[strength - 1]}`
      indicator.style.color = colors[strength - 1]
    } else {
      indicator.textContent = ""
    }
  }
  
  // Auto-resize textareas
  function setupAutoResize() {
    const textareas = document.querySelectorAll("textarea")
  
    textareas.forEach((textarea) => {
      textarea.addEventListener("input", function () {
        this.style.height = "auto"
        this.style.height = this.scrollHeight + "px"
      })
    })
  }
  
  // Confirmation dialogs
  function setupConfirmations() {
    const dangerButtons = document.querySelectorAll(".btn-danger")
  
    dangerButtons.forEach((button) => {
      if (!button.hasAttribute("onclick")) {
        button.addEventListener("click", (e) => {
          if (!confirm("Вы уверены, что хотите выполнить это действие?")) {
            e.preventDefault()
          }
        })
      }
    })
  }
  
  // Initialize everything when DOM is loaded
  document.addEventListener("DOMContentLoaded", () => {
    initTheme()
    setupFileUpload()
    setupDragAndDrop()
    handleUrlNotifications()
    setupFormSubmission()
    setupPasswordStrength()
    setupAutoResize()
    setupConfirmations()
  
    // Add fade-in animation to main content
    const container = document.querySelector(".container")
    if (container) {
      container.classList.add("fade-in")
    }
  })
  
  // Handle back button
  window.addEventListener("popstate", () => {
    location.reload()
  })
  
  // Keyboard shortcuts
  document.addEventListener("keydown", (e) => {
    // Ctrl/Cmd + K for theme toggle
    if ((e.ctrlKey || e.metaKey) && e.key === "k") {
      e.preventDefault()
      toggleTheme()
    }
  
    // Escape to close modals
    if (e.key === "Escape") {
      const modals = document.querySelectorAll(".modal")
      modals.forEach((modal) => {
        if (modal.style.display === "block") {
          modal.style.display = "none"
        }
      })
    }
  })
  
  // API Helper Functions
  async function fetchUserData(userId) {
    try {
      const response = await fetch(`/api/user/${userId}`, {
        credentials: "include",
      })
  
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
  
      return await response.json()
    } catch (error) {
      console.error("Error fetching user data:", error)
      throw error
    }
  }
  
  // Enhanced Image Error Handling
  function handleImageError(img) {
    if (img.src !== "/static/default_avatar.png") {
      img.src = "/static/default_avatar.png"
    }
  }
  
  // Add error handling to all images on page load
  document.addEventListener("DOMContentLoaded", () => {
    const images = document.querySelectorAll("img")
    images.forEach((img) => {
      img.addEventListener("error", () => handleImageError(img))
    })
  })
  
  // Search functionality with debouncing
  function debounce(func, wait) {
    let timeout
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout)
        func(...args)
      }
      clearTimeout(timeout)
      timeout = setTimeout(later, wait)
    }
  }
  
  // Enhanced search with highlighting
  function highlightSearchTerm(text, searchTerm) {
    if (!searchTerm) return text
  
    const regex = new RegExp(`(${searchTerm})`, "gi")
    return text.replace(regex, '<span class="search-highlight">$1</span>')
  }
  
  // Loading state management
  function showLoading(element) {
    const overlay = document.createElement("div")
    overlay.className = "loading-overlay"
    overlay.innerHTML = '<div class="loading-spinner"></div>'
  
    element.style.position = "relative"
    element.appendChild(overlay)
  }
  
  function hideLoading(element) {
    const overlay = element.querySelector(".loading-overlay")
    if (overlay) {
      overlay.remove()
    }
  }
  
  // Enhanced form validation with better UX
  function validateFormField(field) {
    const value = field.value.trim()
    const fieldName = field.name
    let isValid = true
    let errorMessage = ""
  
    // Remove existing error styling
    field.classList.remove("error")
    const existingError = field.parentNode.querySelector(".field-error")
    if (existingError) {
      existingError.remove()
    }
  
    // Validate based on field type and name
    if (field.hasAttribute("required") && !value) {
      isValid = false
      errorMessage = "Это поле обязательно для заполнения"
    } else if (fieldName === "email" && value) {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
      if (!emailRegex.test(value)) {
        isValid = false
        errorMessage = "Введите корректный email адрес"
      }
    } else if (fieldName === "password" && value && value.length < 6) {
      isValid = false
      errorMessage = "Пароль должен содержать минимум 6 символов"
    }
  
    if (!isValid) {
      field.classList.add("error")
      const errorDiv = document.createElement("div")
      errorDiv.className = "field-error"
      errorDiv.textContent = errorMessage
      errorDiv.style.cssText = `
        color: var(--danger);
        font-size: 0.875rem;
        margin-top: 0.25rem;
      `
      field.parentNode.appendChild(errorDiv)
    }
  
    return isValid
  }
  
  // Real-time form validation
  function setupRealTimeValidation() {
    const formFields = document.querySelectorAll(".form-input, .form-select")
  
    formFields.forEach((field) => {
      field.addEventListener("blur", () => validateFormField(field))
      field.addEventListener(
        "input",
        debounce(() => {
          if (field.classList.contains("error")) {
            validateFormField(field)
          }
        }, 500),
      )
    })
  }
  
  // Initialize enhanced features
  document.addEventListener("DOMContentLoaded", () => {
    setupRealTimeValidation()
  })
  