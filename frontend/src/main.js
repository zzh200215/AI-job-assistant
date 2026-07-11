import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { installElement } from './plugins/element'
import './plugins/element.css'
import './styles/main.css'
import './styles/panels.css'

const app = createApp(App)

installElement(app)
app.use(createPinia())
app.use(router)
app.mount('#app')
