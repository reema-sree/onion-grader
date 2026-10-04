/**
 * AgriGrade IndexedDB Offline Queue Management
 * Stores lots, images, and device-computed inspection results locally.
 */

const DB_NAME = 'agrigrade_db';
const DB_VERSION = 1;
const STORE_NAME = 'offline_lots';

let dbInstance = null;

export function initDB() {
  return new Promise((resolve, reject) => {
    if (dbInstance) return resolve(dbInstance);

    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'client_lot_id' });
        store.createIndex('sync_status', 'sync_status', { unique: false });
        store.createIndex('created_at', 'created_at', { unique: false });
      }
    };

    request.onsuccess = (event) => {
      dbInstance = event.target.result;
      resolve(dbInstance);
    };

    request.onerror = (event) => {
      console.error('[IndexedDB] Error initializing database:', event.target.error);
      reject(event.target.error);
    };
  });
}

export async function saveOfflineLot(lotData) {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_NAME], 'readwrite');
    const store = tx.objectStore(STORE_NAME);

    const record = {
      client_lot_id: lotData.client_lot_id || `offline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      farmer_name: lotData.farmer_name,
      centre_id: lotData.centre_id || 1,
      weight_kg: parseFloat(lotData.weight_kg) || 0.0,
      lot_number: lotData.lot_number || `LOT-OFFLINE-${Date.now().toString().slice(-6)}`,
      computation_source: 'device',
      is_device_computed: true,
      detections: lotData.detections || [],
      grade_result: lotData.grade_result || null,
      sync_status: 'pending', // 'pending' | 'syncing' | 'synced' | 'failed'
      sync_error: null,
      server_lot_id: null,
      created_at: lotData.created_at || new Date().toISOString(),
      updated_at: new Date().toISOString(),
      image_data_url: lotData.image_data_url || null,
    };

    const req = store.put(record);
    req.onsuccess = () => resolve(record);
    req.onerror = (e) => reject(e.target.error);
  });
}

export async function getAllOfflineLots() {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_NAME], 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const req = store.getAll();

    req.onsuccess = () => {
      const records = req.result || [];
      records.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      resolve(records);
    };
    req.onerror = (e) => reject(e.target.error);
  });
}

export async function updateLotSyncStatus(clientLotId, syncStatus, serverLotId = null, errorMessage = null) {
  const db = await initDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_NAME], 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const getReq = store.get(clientLotId);

    getReq.onsuccess = () => {
      const record = getReq.result;
      if (!record) return resolve(null);

      record.sync_status = syncStatus;
      record.updated_at = new Date().toISOString();
      if (serverLotId) record.server_lot_id = serverLotId;
      if (errorMessage) record.sync_error = errorMessage;
      else if (syncStatus === 'synced') record.sync_error = null;

      const putReq = store.put(record);
      putReq.onsuccess = () => resolve(record);
      putReq.onerror = (e) => reject(e.target.error);
    };
    getReq.onerror = (e) => reject(e.target.error);
  });
}

export async function syncAllPendingLots(apiBaseUrl = '') {
  const lots = await getAllOfflineLots();
  const pendingLots = lots.filter(l => l.sync_status === 'pending' || l.sync_status === 'failed');

  const results = {
    synced: 0,
    failed: 0,
    details: [],
  };

  for (const lot of pendingLots) {
    try {
      await updateLotSyncStatus(lot.client_lot_id, 'syncing');

      const payload = {
        client_lot_id: lot.client_lot_id,
        farmer_name: lot.farmer_name,
        centre_id: lot.centre_id,
        weight_kg: lot.weight_kg,
        lot_number: lot.lot_number,
        computation_source: 'device',
        is_device_computed: true,
        detections: lot.detections.map(d => ({
          bbox: d.bbox,
          mask_polygon: d.mask_polygon || null,
          original_class: d.original_class || d.class,
          current_class: d.current_class || d.class,
          confidence: d.confidence || 1.0,
          diameter_cm: d.diameter_cm || null,
          is_overridden: !!d.is_overridden,
        })),
        created_at: lot.created_at,
      };

      const response = await fetch(`${apiBaseUrl}/lots/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errText}`);
      }

      const serverData = await response.json();
      await updateLotSyncStatus(lot.client_lot_id, 'synced', serverData.id);
      results.synced++;
      results.details.push({ client_lot_id: lot.client_lot_id, status: 'synced', server_id: serverData.id });
    } catch (err) {
      console.error(`[Sync] Failed to sync lot ${lot.client_lot_id}:`, err);
      await updateLotSyncStatus(lot.client_lot_id, 'failed', null, err.message);
      results.failed++;
      results.details.push({ client_lot_id: lot.client_lot_id, status: 'failed', error: err.message });
    }
  }

  return results;
}
