import { reactive } from 'vue'

export const toastState = reactive({
  visible: false,
  message: '',
  type: 'info',   // 'info' | 'error'
})

let _timer = null

export const toast = {
  show(message, type = 'info', duration = 3500) {
    if (_timer) clearTimeout(_timer)
    toastState.message = message
    toastState.type    = type
    toastState.visible = true
    _timer = setTimeout(() => { toastState.visible = false }, duration)
  },
}
