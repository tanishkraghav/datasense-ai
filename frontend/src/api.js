import axios from 'axios'

let API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
// Ensure no trailing slash to prevent double-slash routes
API_BASE_URL = API_BASE_URL.replace(/\/+$/, '')

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // 60 seconds timeout to handle Render cold starts
})

export const uploadDataset = async (file) => {
  const formData = new FormData()
  formData.append('file', file)
  const response = await api.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

export const listDatasets = async () => {
  const response = await api.get('/datasets')
  return response.data
}

export const getProfile = async (datasetId) => {
  const response = await api.get(`/datasets/${datasetId}/profile`)
  return response.data
}

export const generateReport = async (datasetId) => {
  const response = await api.post(`/datasets/${datasetId}/report`)
  return response.data
}

export const getReport = async (datasetId) => {
  const response = await api.get(`/datasets/${datasetId}/report`)
  return response.data
}

export const sendQuery = async (datasetId, question) => {
  const response = await api.post(`/datasets/${datasetId}/query`, { question })
  return response.data
}

export const getChatHistory = async (datasetId) => {
  const response = await api.get(`/datasets/${datasetId}/chat-history`)
  return response.data
}

export const getDatasetRows = async (datasetId, indicesStr) => {
  const params = indicesStr ? { indices: indicesStr } : {}
  const response = await api.get(`/datasets/${datasetId}/rows`, { params })
  return response.data
}

export default api
