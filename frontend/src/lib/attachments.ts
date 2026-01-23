// frontend\src\lib\attachments.ts

export function imageDownloadUrl(imagePath: string) {
  return `/api/images/download?path=${encodeURIComponent(imagePath)}`;
}

export function tableDownloadUrl(tablePath: string) {
  return `/api/tables/download?path=${encodeURIComponent(tablePath)}`;
}
