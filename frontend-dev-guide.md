# OpenOrganoid-Server Frontend Developer Guide

## 🚀 Quick Start for Frontend Integration

This guide helps frontend developers integrate with the OpenOrganoid-Server API effectively.

## 📡 API Overview

### Base Configuration
- **Base URL**: `http://localhost:8000/api/v1` (development)
- **Authentication**: JWT Bearer tokens + API Keys
- **Content-Type**: `application/json`
- **Documentation**: `http://localhost:8000/docs` (OpenAPI/Swagger)

### API Architecture
```
Frontend Client
      ↓
API Gateway (Port 8000)
      ↓
┌─────────────────────────────────┐
│  Microservices Architecture    │
├─────────────────────────────────┤
│ • Dataset Service (Port 8001)  │
│ • File Service (Port 8002)     │
│ • Analytics Service (Port 8003)│
└─────────────────────────────────┘
      ↓
┌─────────────────────────────────┐
│ Data Layer                      │
├─────────────────────────────────┤
│ • PostgreSQL (Port 5432)       │
│ • Redis (Port 6379)            │
│ • DataLad + Git-Annex          │
└─────────────────────────────────┘
```

## 🔐 Authentication Integration

### 1. User Registration & Login

#### Register New User
```javascript
const registerUser = async (userData) => {
  const response = await fetch('/api/v1/auth/register', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      email: userData.email,
      username: userData.username,
      password: userData.password, // Must meet complexity requirements
    }),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
  
  return await response.json();
};
```

#### User Login
```javascript
const loginUser = async (email, password) => {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      email: email,
      password: password,
    }),
  });
  
  if (!response.ok) {
    throw new Error('Login failed');
  }
  
  const data = await response.json();
  
  // Store tokens securely
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  
  return data;
};
```

### 2. Token Management

#### Automatic Token Refresh
```javascript
class ApiClient {
  constructor() {
    this.baseURL = 'http://localhost:8000/api/v1';
    this.accessToken = localStorage.getItem('access_token');
    this.refreshToken = localStorage.getItem('refresh_token');
  }
  
  async refreshAccessToken() {
    const response = await fetch(`${this.baseURL}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        refresh_token: this.refreshToken,
      }),
    });
    
    if (response.ok) {
      const data = await response.json();
      this.accessToken = data.access_token;
      localStorage.setItem('access_token', data.access_token);
      return true;
    }
    
    // Refresh failed, redirect to login
    this.logout();
    return false;
  }
  
  async apiRequest(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    
    const config = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.accessToken}`,
        ...options.headers,
      },
    };
    
    let response = await fetch(url, config);
    
    // Auto-refresh token on 401
    if (response.status === 401 && this.refreshToken) {
      const refreshed = await this.refreshAccessToken();
      if (refreshed) {
        config.headers['Authorization'] = `Bearer ${this.accessToken}`;
        response = await fetch(url, config);
      }
    }
    
    return response;
  }
  
  logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
  }
}

// Usage
const api = new ApiClient();
```

### 3. API Key Authentication (Alternative)
```javascript
// For service-to-service communication
const apiKeyRequest = async (endpoint, apiKey, options = {}) => {
  return await fetch(`http://localhost:8000/api/v1${endpoint}`, {
    ...options,
    headers: {
      'X-API-Key': apiKey,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
};
```

## 📊 Dataset Management Integration

### 1. List Datasets with Filtering
```javascript
const getDatasets = async (filters = {}) => {
  const params = new URLSearchParams({
    page: filters.page || 1,
    size: filters.size || 20,
    ...(filters.search && { search: filters.search }),
    ...(filters.data_type && { data_type: filters.data_type }),
    ...(filters.visibility && { visibility: filters.visibility }),
  });
  
  const response = await api.apiRequest(`/datasets?${params}`);
  
  if (!response.ok) {
    throw new Error('Failed to fetch datasets');
  }
  
  return await response.json();
};

// Usage example
const datasets = await getDatasets({
  search: 'organoid',
  data_type: 'microscopy',
  page: 1,
  size: 10,
});

console.log(datasets.data); // Array of datasets
console.log(datasets.meta); // Pagination info
```

### 2. Create New Dataset
```javascript
const createDataset = async (datasetData) => {
  const response = await api.apiRequest('/datasets', {
    method: 'POST',
    body: JSON.stringify({
      title: datasetData.title,
      description: datasetData.description,
      visibility: datasetData.visibility || 'private',
      data_schema: datasetData.schema,
      feature_metadata: datasetData.features,
    }),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
  
  return await response.json();
};
```

### 3. Dataset Details
```javascript
const getDatasetDetails = async (datasetId) => {
  const response = await api.apiRequest(`/datasets/${datasetId}`);
  
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Dataset not found');
    }
    throw new Error('Failed to fetch dataset');
  }
  
  return await response.json();
};
```

## 📁 File Upload Integration

### 1. Simple File Upload
```javascript
const uploadFile = async (datasetId, file, filePath = null) => {
  const formData = new FormData();
  formData.append('file', file);
  if (filePath) {
    formData.append('file_path', filePath);
  }
  
  const response = await api.apiRequest(`/datasets/${datasetId}/files`, {
    method: 'POST',
    body: formData,
    headers: {
      // Don't set Content-Type for FormData
      'Authorization': `Bearer ${api.accessToken}`,
    },
  });
  
  if (!response.ok) {
    throw new Error('File upload failed');
  }
  
  return await response.json();
};
```

### 2. Chunked File Upload (Large Files)
```javascript
class ChunkedUploader {
  constructor(file, datasetId, chunkSize = 5 * 1024 * 1024) { // 5MB chunks
    this.file = file;
    this.datasetId = datasetId;
    this.chunkSize = chunkSize;
    this.totalChunks = Math.ceil(file.size / chunkSize);
  }
  
  async upload(onProgress = null) {
    for (let chunkIndex = 0; chunkIndex < this.totalChunks; chunkIndex++) {
      const start = chunkIndex * this.chunkSize;
      const end = Math.min(start + this.chunkSize, this.file.size);
      const chunk = this.file.slice(start, end);
      
      const formData = new FormData();
      formData.append('file', chunk);
      formData.append('file_path', this.file.name);
      formData.append('chunk_index', chunkIndex);
      formData.append('total_chunks', this.totalChunks);
      
      const response = await api.apiRequest(`/datasets/${this.datasetId}/files`, {
        method: 'POST',
        body: formData,
        headers: {
          'Authorization': `Bearer ${api.accessToken}`,
        },
      });
      
      if (!response.ok) {
        throw new Error(`Chunk ${chunkIndex} upload failed`);
      }
      
      if (onProgress) {
        onProgress({
          chunkIndex: chunkIndex + 1,
          totalChunks: this.totalChunks,
          progress: ((chunkIndex + 1) / this.totalChunks) * 100,
        });
      }
    }
    
    return { success: true, message: 'Upload completed' };
  }
}

// Usage
const uploader = new ChunkedUploader(file, datasetId);
await uploader.upload((progress) => {
  console.log(`Upload ${progress.progress.toFixed(1)}% complete`);
});
```

## 🔍 Search & Discovery

### Advanced Search
```javascript
const searchDatasets = async (searchQuery) => {
  const response = await api.apiRequest('/datasets/search', {
    method: 'POST',
    body: JSON.stringify({
      query: searchQuery.text,
      filters: {
        data_types: searchQuery.dataTypes,
        organisms: searchQuery.organisms,
        techniques: searchQuery.techniques,
        file_formats: searchQuery.fileFormats,
      },
      facets: ['data_type', 'organism', 'technique'],
      sort: searchQuery.sort || 'relevance',
      page: searchQuery.page || 1,
      size: searchQuery.size || 20,
    }),
  });
  
  return await response.json();
};
```

## 📥 Data Export & Download

### 1. Dataset Download
```javascript
const downloadDataset = async (datasetId, format = 'zip', version = null) => {
  const params = new URLSearchParams({
    format,
    ...(version && { version }),
  });
  
  const response = await api.apiRequest(`/datasets/${datasetId}/download?${params}`);
  
  if (!response.ok) {
    throw new Error('Download failed');
  }
  
  // Handle file download
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `dataset-${datasetId}.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
};
```

### 2. Real-time Data Streaming
```javascript
const streamDataset = async (datasetId, format = 'json', onData = null, onError = null) => {
  const response = await api.apiRequest(`/datasets/${datasetId}/stream?format=${format}`);
  
  if (!response.ok) {
    throw new Error('Stream failed to start');
  }
  
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  
  try {
    while (true) {
      const { done, value } = await reader.read();
      
      if (done) break;
      
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n').filter(line => line.trim());
      
      for (const line of lines) {
        try {
          const data = JSON.parse(line);
          if (onData) onData(data);
        } catch (e) {
          if (onError) onError(e);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
};

// Usage
await streamDataset(
  'dataset-id',
  'json',
  (data) => console.log('Received:', data),
  (error) => console.error('Stream error:', error)
);
```

## 🔄 Real-time Updates with WebSockets

```javascript
class DatasetWebSocket {
  constructor(datasetId) {
    this.datasetId = datasetId;
    this.ws = null;
    this.listeners = {};
  }
  
  connect() {
    const token = localStorage.getItem('access_token');
    this.ws = new WebSocket(`ws://localhost:8000/ws/datasets/${this.datasetId}?token=${token}`);
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.emit(data.type, data.payload);
    };
    
    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      // Implement reconnection logic
    };
  }
  
  on(event, callback) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
  }
  
  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(callback => callback(data));
    }
  }
  
  disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

// Usage
const datasetWS = new DatasetWebSocket('dataset-id');
datasetWS.on('file_uploaded', (data) => {
  console.log('New file uploaded:', data);
});
datasetWS.on('validation_complete', (data) => {
  console.log('Validation completed:', data);
});
datasetWS.connect();
```

## 🎨 React Integration Examples

### Custom Hook for Datasets
```javascript
import { useState, useEffect } from 'react';

export const useDatasets = (filters = {}) => {
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [meta, setMeta] = useState({});
  
  useEffect(() => {
    const fetchDatasets = async () => {
      try {
        setLoading(true);
        const response = await getDatasets(filters);
        setDatasets(response.data);
        setMeta(response.meta);
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    
    fetchDatasets();
  }, [JSON.stringify(filters)]);
  
  return { datasets, loading, error, meta };
};

// Component usage
const DatasetList = () => {
  const [filters, setFilters] = useState({ page: 1, size: 10 });
  const { datasets, loading, error, meta } = useDatasets(filters);
  
  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  
  return (
    <div>
      {datasets.map(dataset => (
        <div key={dataset.id}>
          <h3>{dataset.title}</h3>
          <p>{dataset.description}</p>
        </div>
      ))}
      
      <Pagination 
        current={meta.page} 
        total={meta.total_pages}
        onChange={(page) => setFilters({...filters, page})}
      />
    </div>
  );
};
```

## 🚨 Error Handling

### Standard Error Response Format
```javascript
{
  "detail": "Error message",
  "error_code": "VALIDATION_ERROR",
  "details": {
    "field": "specific error details"
  }
}
```

### Global Error Handler
```javascript
const handleApiError = (error, response) => {
  switch (response.status) {
    case 400:
      return 'Bad request - please check your input';
    case 401:
      return 'Authentication required - please log in';
    case 403:
      return 'You do not have permission for this action';
    case 404:
      return 'Resource not found';
    case 422:
      return error.detail?.message || 'Validation error';
    case 429:
      return 'Too many requests - please try again later';
    case 500:
      return 'Server error - please try again later';
    default:
      return error.detail || 'An unexpected error occurred';
  }
};
```

## 🔧 Development Tools

### Environment Setup
```bash
# Start the development server
docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d

# API will be available at:
# - Main API: http://localhost:8000
# - Documentation: http://localhost:8000/docs
# - Database: localhost:5432
# - Redis: localhost:6379
```

### Testing API Endpoints
```javascript
// Use the built-in API documentation at http://localhost:8000/docs
// Or test with curl:

// Login
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'

// Get datasets
curl -X GET "http://localhost:8000/api/v1/datasets" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 📚 Additional Resources

- **API Documentation**: `http://localhost:8000/docs` (Interactive Swagger UI)
- **ReDoc Documentation**: `http://localhost:8000/redoc` (Alternative API docs)
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`
- **Health Check**: `http://localhost:8000/health`

## 🐛 Common Issues & Solutions

### 1. CORS Issues
Ensure your frontend domain is added to `CORS_ORIGINS` in `.env`:
```
CORS_ORIGINS=http://localhost:3000,http://localhost:8080,https://yourdomain.com
```

### 2. Token Expiration
Implement automatic token refresh or handle 401 responses gracefully.

### 3. File Upload Timeouts
For large files, increase timeout settings and use chunked uploads.

### 4. WebSocket Connection Issues
Check that the WebSocket endpoint supports your authentication method.

---

**Need Help?** Check the main API documentation or create an issue in the repository.