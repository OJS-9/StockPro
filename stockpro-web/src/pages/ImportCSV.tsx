import { useState, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router'
import { useAuth } from '@clerk/clerk-react'
import toast from 'react-hot-toast'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'

export default function ImportCSV() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { getToken } = useAuth()
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<any[]>([])

  const handleFile = (f: File) => {
    setFile(f)
    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result as string
      const lines = text.split('\n').filter(l => l.trim()).slice(0, 6)
      const headers = lines[0].split(',')
      const rows = lines.slice(1).map(l => {
        const vals = l.split(',')
        return headers.reduce((acc: any, h, i) => { acc[h.trim()] = vals[i]?.trim(); return acc }, {})
      })
      setPreview(rows.slice(0, 5))
    }
    reader.readAsText(f)
  }

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error('No file')
      const formData = new FormData()
      formData.append('file', file)
      formData.append('broker', 'custom')
      const token = await getToken()
      const res = await fetch(`/api/portfolio/${id}/import`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
    onSuccess: () => {
      toast.success('CSV imported successfully')
      navigate(`/portfolio/${id}`)
    },
    onError: () => toast.error('Failed to import CSV'),
  })

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 720, margin: '0 auto', padding: '48px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Link to={`/portfolio/${id}`} style={{ color: '#a8a29e', textDecoration: 'none', fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Icon name="arrow_back" size={16} /> Portfolio
            </Link>
          </div>
          <h1 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>Import from CSV</h1>
          <p style={{ fontSize: 13, color: '#a8a29e' }}>Upload a CSV file with columns: date, symbol, type, shares, price.</p>
        </div>

        {/* FILE UPLOAD */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#a8a29e', marginBottom: 12 }}>Upload file</div>
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
            style={{ border: `2px dashed ${file ? '#22c55e' : '#292524'}`, borderRadius: 14, padding: '40px 24px', textAlign: 'center', cursor: 'pointer', transition: 'border-color 0.2s', background: file ? 'rgba(34,197,94,0.04)' : 'transparent' }}
          >
            <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
            <Icon name={file ? 'check_circle' : 'upload_file'} size={36} />
            <div style={{ marginTop: 12, fontSize: 15, fontWeight: 500 }}>{file ? file.name : 'Drop CSV file here or click to browse'}</div>
            <div style={{ fontSize: 12, color: '#a8a29e', marginTop: 6 }}>Supports .csv files up to 10MB</div>
          </div>
        </div>

        {/* PREVIEW TABLE */}
        {preview.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#a8a29e', marginBottom: 12 }}>Preview ({preview.length} rows)</div>
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 12, overflow: 'hidden', overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', whiteSpace: 'nowrap' }}>
                <thead>
                  <tr>
                    {Object.keys(preview[0]).map(h => (
                      <th key={h} style={{ fontSize: 10.5, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', textAlign: 'start', padding: '10px 16px', borderBottom: '1px solid #292524' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.map((row, i) => (
                    <tr key={i}>
                      {Object.values(row).map((v: any, j) => (
                        <td key={j} style={{ padding: '10px 16px', borderBottom: i < preview.length - 1 ? '1px solid rgba(41,37,36,0.5)' : 'none', fontSize: 12.5, color: '#fafaf9', fontVariantNumeric: 'tabular-nums' }}>{v}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 10 }}>
          <Link to={`/portfolio/${id}`} style={{ flex: 1, padding: '12px', borderRadius: 10, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', fontSize: 14, fontWeight: 500, textAlign: 'center', textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            Cancel
          </Link>
          <button
            onClick={() => mutation.mutate()}
            disabled={!file || mutation.isPending}
            style={{ flex: 2, padding: '12px', borderRadius: 10, border: 'none', background: file ? '#d6d3d1' : '#292524', color: file ? '#0c0a09' : '#a8a29e', fontSize: 14, fontWeight: 600, cursor: file ? 'pointer' : 'not-allowed' }}
          >
            {mutation.isPending ? 'Importing...' : 'Import Transactions'}
          </button>
        </div>
      </main>
    </div>
  )
}
