// Service Worker para WhatsApp CRM PWA
const CACHE_NAME = 'crm-whatsapp-v1';

// Manejar clic en notificación (abre/enfoca la app)
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if ('focus' in client) return client.focus();
            }
            return clients.openWindow('/');
        })
    );
});

// Archivos de la shell de la app que se cachean al instalar
const SHELL_ASSETS = [
  '/static/manifest.json',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap',
  'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap',
];

// Instalar: cachear la shell de la app
self.addEventListener('install', (event) => {
  console.log('[SW] Instalando Service Worker...');
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(SHELL_ASSETS);
    })
  );
  // Activar inmediatamente sin esperar que cierren las pestañas
  self.skipWaiting();
});

// Activar: limpiar caches viejos
self.addEventListener('activate', (event) => {
  console.log('[SW] Service Worker activado');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  // Tomar control de todas las páginas inmediatamente
  self.clients.claim();
});

// Fetch: Network First (siempre intenta la red, si falla usa cache)
// Esto es ideal para un CRM que necesita datos frescos
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // No interceptar peticiones de la API (siempre frescas)
  if (request.url.includes('/api/') || request.url.includes('/webhook')) {
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        // Si la respuesta es válida, guardarla en cache
        if (response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Si falla la red, intentar servir desde cache
        return caches.match(request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // Si no hay cache, mostrar página offline genérica
          if (request.mode === 'navigate') {
            return new Response(
              `<!DOCTYPE html>
              <html>
              <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Sin conexión - CRM WhatsApp</title>
                <style>
                  body { font-family: 'Inter', sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #102212; color: white; text-align: center; }
                  .container { padding: 2rem; }
                  h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
                  p { color: #9ca3af; font-size: 0.9rem; }
                  .icon { font-size: 4rem; margin-bottom: 1rem; opacity: 0.5; }
                  button { margin-top: 1.5rem; padding: 0.75rem 2rem; background: #13ec25; color: #102212; border: none; border-radius: 12px; font-weight: 600; cursor: pointer; font-size: 0.9rem; }
                </style>
              </head>
              <body>
                <div class="container">
                  <div class="icon">📡</div>
                  <h1>Sin conexión</h1>
                  <p>No se pudo conectar al servidor.<br>Verificá tu conexión a internet.</p>
                  <button onclick="location.reload()">Reintentar</button>
                </div>
              </body>
              </html>`,
              { headers: { 'Content-Type': 'text/html' } }
            );
          }
        });
      })
  );
});
