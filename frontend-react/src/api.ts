import axios from 'axios'

export const api = axios.create({ baseURL: '/api', headers: { 'Content-Type': 'application/json' } })
let memoryToken = sessionStorage.getItem('mawos_token')
export const setToken = (token: string | null) => { memoryToken = token; token ? sessionStorage.setItem('mawos_token', token) : sessionStorage.removeItem('mawos_token') }
api.interceptors.request.use((config) => { if (memoryToken) config.headers.Authorization = `Bearer ${memoryToken}`; return config })
api.interceptors.response.use((response) => response, (error) => { if (error.response?.status === 401 && window.location.pathname !== '/login') { setToken(null); window.location.assign('/login') } return Promise.reject(error) })
export const apiError = (error: unknown) => axios.isAxiosError(error) ? (error.response?.data?.detail || error.response?.data?.error || error.message) : 'Request failed'
