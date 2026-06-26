import { useStore } from '../store'

// Start/stop/restart the background service. Mirrors the legacy App.handleService:
// flip to 'connecting' immediately for responsive feedback; the main process
// broadcasts the real status (connected / disconnected) shortly after.
export async function serviceAction(action) {
  try {
    useStore.getState().setStatus('connecting')
    await window.api.service[action]()
  } catch (e) {
    console.error(`service ${action} failed`, e)
  }
}
