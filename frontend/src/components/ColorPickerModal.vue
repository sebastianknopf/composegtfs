<script setup>
/**
 * ColorPickerModal - color picker dialog (HSV gradient + hue slider).
 *
 * Props:
 *   open        - boolean  - controlled open state
 *   modelValue  - string   - hex color WITHOUT '#' (6 chars), or empty string
 *   label       - string   - dialog headline / field label
 *
 * Emits:
 *   update:modelValue(hex)  - confirmed new color (6-char hex or empty for clear)
 *   close                   - user dismissed the dialog
 */
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import '@material/web/dialog/dialog.js'
import '@material/web/button/text-button.js'
import '@material/web/button/filled-button.js'
import '@material/web/icon/icon.js'

const { t } = useI18n()

const props = defineProps({
  open:       { type: Boolean, default: false },
  modelValue: { type: String,  default: '' },
  label:      { type: String,  default: '' },
})
const emit = defineEmits(['update:modelValue', 'close'])

const hue        = ref(0)
const saturation = ref(100)
const colorValue = ref(100)
const hexInput   = ref('')
const hexError   = ref('')

const HEX_RE = /^[0-9A-Fa-f]{6}$/

function hsvToRgb(h, s, v) {
  s /= 100; v /= 100
  const i = Math.floor(h / 60) % 6
  const f = (h / 60) - Math.floor(h / 60)
  const p = v * (1 - s)
  const q = v * (1 - f * s)
  const u = v * (1 - (1 - f) * s)
  const map = [[v, u, p], [q, v, p], [p, v, u], [p, q, v], [u, p, v], [v, p, q]]
  return map[i].map(x => Math.round(x * 255))
}

function rgbToHex(r, g, b) {
  return [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('').toUpperCase()
}

function hexToRgb(hex) {
  const n = parseInt(hex, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function rgbToHsv(r, g, b) {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const d = max - min
  let h = 0
  const s = max === 0 ? 0 : d / max
  const v = max
  if (d !== 0) {
    if      (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6
    else if (max === g) h = ((b - r) / d + 2) / 6
    else                h = ((r - g) / d + 4) / 6
  }
  return [Math.round(h * 360), Math.round(s * 100), Math.round(v * 100)]
}

const currentHex = computed(() => {
  const [r, g, b] = hsvToRgb(hue.value, saturation.value, colorValue.value)
  return rgbToHex(r, g, b)
})

const svStyle = computed(() => ({
  background: `linear-gradient(to bottom, transparent, #000), linear-gradient(to right, #fff, hsl(${hue.value}, 100%, 50%))`,
}))

const cursorStyle = computed(() => ({
  left: saturation.value + '%',
  top:  (100 - colorValue.value) + '%',
}))

const dialogRef = ref(null)

watch(() => props.open, (val) => {
  const el = dialogRef.value
  if (val) {
    hexError.value = ''
    const hex = props.modelValue
    if (hex && HEX_RE.test(hex)) {
      const [r, g, b] = hexToRgb(hex)
      const [h, s, v] = rgbToHsv(r, g, b)
      hue.value        = h
      saturation.value = s
      colorValue.value = v
    } else {
      hue.value        = 0
      saturation.value = 100
      colorValue.value = 100
    }
    hexInput.value = hex ? hex.toUpperCase() : ''
    requestAnimationFrame(() => el?.show?.())
  } else {
    el?.close?.()
  }
})

watch(currentHex, (hex) => { hexInput.value = hex })

const svBoxRef = ref(null)
const dragging = ref(false)

function onSvPointerDown(e) {
  dragging.value = true
  updateSv(e)
  window.addEventListener('pointermove', onWindowMove)
  window.addEventListener('pointerup',   onWindowUp)
}
function onWindowMove(e) { if (dragging.value) updateSv(e) }
function onWindowUp() {
  dragging.value = false
  window.removeEventListener('pointermove', onWindowMove)
  window.removeEventListener('pointerup',   onWindowUp)
}
function updateSv(e) {
  const box = svBoxRef.value?.getBoundingClientRect()
  if (!box) return
  saturation.value = Math.round(Math.max(0, Math.min(1, (e.clientX - box.left) / box.width))  * 100)
  colorValue.value = Math.round(Math.max(0, Math.min(1, 1 - (e.clientY - box.top)  / box.height)) * 100)
}
onUnmounted(() => {
  window.removeEventListener('pointermove', onWindowMove)
  window.removeEventListener('pointerup',   onWindowUp)
})

function onHexInput(e) {
  const raw = e.target.value.replace(/^#/, '').toUpperCase()
  hexInput.value = raw
  hexError.value = ''
  if (HEX_RE.test(raw)) {
    const [r, g, b] = hexToRgb(raw)
    const [h, s, v] = rgbToHsv(r, g, b)
    hue.value        = h
    saturation.value = s
    colorValue.value = v
  }
}

function onConfirm() {
  emit('update:modelValue', currentHex.value)
  emit('close')
}
function onClear() {
  emit('update:modelValue', '')
  emit('close')
}
function onCancel() { emit('close') }
</script>

<template>
  <md-dialog ref="dialogRef" class="cp-dialog" @closed="onCancel">

    <div slot="headline">{{ label || t('color_picker.dialog_label') }}</div>

    <div slot="content" class="cp-content">
      <div ref="svBoxRef" class="cp-sv-box" :style="svStyle" @pointerdown.prevent="onSvPointerDown">
        <span class="cp-sv-cursor" :style="cursorStyle" />
      </div>

      <div class="cp-hue-row">
        <span class="cp-preview" :style="{ background: '#' + currentHex }" />
        <input
          type="range" min="0" max="360"
          class="cp-hue-slider"
          :value="hue"
          @input="hue = Number($event.target.value)"
        />
      </div>

      <div class="cp-hex-wrap">
        <span class="cp-hex-hash">#</span>
        <input
          type="text" maxlength="6" placeholder="RRGGBB"
          class="cp-hex-input"
          :value="hexInput"
          @input="onHexInput"
        />
      </div>
      <span v-if="hexError" class="cp-hex-error">{{ hexError }}</span>
    </div>

    <div slot="actions" class="cp-actions">
      <md-text-button @click="onClear">{{ t('color_picker.clear') }}</md-text-button>
      <div class="cp-actions-right">
        <md-text-button @click="onCancel">{{ t('color_picker.cancel') }}</md-text-button>
        <md-filled-button @click="onConfirm">{{ t('color_picker.confirm') }}</md-filled-button>
      </div>
    </div>

  </md-dialog>
</template>

<style scoped>
.cp-dialog {
  --md-dialog-container-shape: 6px;
}

.cp-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}

.cp-sv-box {
  height: 160px;
  border-radius: 8px;
  position: relative;
  cursor: crosshair;
  touch-action: none;
  user-select: none;
}

.cp-sv-cursor {
  position: absolute;
  width: 16px; height: 16px;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 0 0 1.5px rgba(0,0,0,0.5);
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.cp-hue-row {
  display: flex; align-items: center; gap: 10px;
}

.cp-preview {
  width: 28px; height: 28px;
  border-radius: 50%;
  flex-shrink: 0;
  border: 2px solid var(--md-sys-color-outline);
  display: block;
}

.cp-hue-slider {
  flex: 1;
  -webkit-appearance: none;
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(
    to right,
    hsl(0,100%,50%), hsl(30,100%,50%), hsl(60,100%,50%),
    hsl(90,100%,50%), hsl(120,100%,50%), hsl(150,100%,50%),
    hsl(180,100%,50%), hsl(210,100%,50%), hsl(240,100%,50%),
    hsl(270,100%,50%), hsl(300,100%,50%), hsl(330,100%,50%), hsl(360,100%,50%)
  );
  border: none; outline: none; cursor: pointer;
}
.cp-hue-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px; height: 18px; border-radius: 50%;
  background: #fff;
  border: 2px solid rgba(0,0,0,0.3);
  box-shadow: 0 1px 4px rgba(0,0,0,0.3);
  cursor: grab;
}
.cp-hue-slider::-moz-range-thumb {
  width: 18px; height: 18px; border-radius: 50%;
  background: #fff;
  border: 2px solid rgba(0,0,0,0.3);
  cursor: grab;
}

.cp-hex-wrap {
  display: flex; align-items: center;
  border: 1px solid var(--md-sys-color-outline);
  border-radius: 8px;
  padding: 6px 10px;
  gap: 2px;
}
.cp-hex-hash {
  font-family: monospace;
  color: var(--md-sys-color-on-surface-variant);
}
.cp-hex-input {
  background: none; border: none; outline: none;
  font-family: monospace; font-size: 14px;
  color: var(--md-sys-color-on-surface);
  width: 100%;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.cp-hex-error {
  display: block;
  font-size: 12px;
  color: var(--md-sys-color-error);
}

.cp-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.cp-actions-right { display: flex; gap: 4px; }
</style>
