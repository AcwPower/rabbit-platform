import {defineConfig} from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({plugins:[vue(),tailwindcss()],base:'/party/',server:{proxy:{'/party/api':{target:'http://127.0.0.1:8101',rewrite:path=>path.replace('/party','')}}}})
