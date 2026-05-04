<script setup>
import { onMounted, onActivated, onBeforeUnmount, ref } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { settingsStore } from '@/stores/settings.js'

const mapContainer = ref(null)
let map = null

onMounted(async () => {
  // Ensure settings are available (may already be loaded)
  if (!settingsStore.state.mapTileUrl) {
    await settingsStore.load()
  }
  map = new maplibregl.Map({
    container: mapContainer.value,
    style: settingsStore.state.mapTileUrl,
    center: [10.0, 51.0],
    zoom: 6,
  })
  map.addControl(new maplibregl.NavigationControl(), 'top-right')
})

// When the view is re-activated from KeepAlive cache, resize the map
// so it fills the container correctly (it may have been hidden).
onActivated(() => {
  map?.resize()
})

onBeforeUnmount(() => {
  map?.remove()
  map = null
})
</script>

<template>
  <div ref="mapContainer" class="network-map" />
</template>

<style scoped>
.network-map {
  width: 100%;
  height: 100%;
}
</style>

<style scoped>
.network-map {
  width: 100%;
  height: 100%;
}
</style>
