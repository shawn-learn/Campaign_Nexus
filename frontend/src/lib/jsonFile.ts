// Small helpers for downloading generated JSON and reading an uploaded JSON file.

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function pickJsonFile(): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json,application/json'
    input.onchange = () => {
      const file = input.files?.[0]
      if (!file) return reject(new Error('no file selected'))
      const reader = new FileReader()
      reader.onload = () => {
        try {
          resolve(JSON.parse(String(reader.result)))
        } catch {
          reject(new Error('not valid JSON'))
        }
      }
      reader.onerror = () => reject(reader.error ?? new Error('read failed'))
      reader.readAsText(file)
    }
    input.click()
  })
}

function slug(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'export'
}

export function exportFilename(base: string, name: string): string {
  return `${base}-${slug(name)}.json`
}
