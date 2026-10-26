const express = require('express');
const multer = require('multer');
const { S3Client, PutObjectCommand } = require('@aws-sdk/client-s3');

const app = express();

const MAX_FILE_SIZE = 1 * 1024 * 1024;

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: MAX_FILE_SIZE },
  fileFilter: (req, file, cb) => {
    const isTxt =
      file.mimetype === 'text/plain' &&
      file.originalname.toLowerCase().endsWith('.txt');

    if (!isTxt) {
      return cb(new Error('ONLY_TXT_ALLOWED'));
    }

    cb(null, true);
  },
});

const s3 = new S3Client({
  region: process.env.AWS_REGION
});

const BUCKET = process.env.BUCKET_NAME;
const PORT = process.env.PORT || 3000;

app.get('/', (req, res) => {
  res.send(`
<h1>Uploader</h1>
<form method="POST" action="/upload" enctype="multipart/form-data">
<input type="file" name="txtfile" accept=".txt" required>
<p>Only .txt files, max 1MB</p>
<button type="submit">Upload</button>
</form>
`);
});

app.post('/upload', (req, res) => {
  upload.single('txtfile')(req, res, async (err) => {
    if (err) {
      if (err.code === 'LIMIT_FILE_SIZE') {
        return res.status(413).send(
          '<p>Upload failed: file exceeds the 1MB limit.</p><a href="/">Try again</a>'
        );
      }

      if (err.message === 'ONLY_TXT_ALLOWED') {
        return res.status(415).send(
          '<p>Upload failed: only .txt files are allowed.</p><a href="/">Try again</a>'
        );
      }

      return res.status(400).send(
        '<p>Upload failed: ' +
        err.message +
        '</p><a href="/">Try again</a>'
      );
    }

    if (!req.file) {
      return res.status(400).send(
        'No file selected.'
      );
    }

    try {
      await s3.send(
        new PutObjectCommand({
          Bucket: BUCKET,
          Key: 'shared.txt',
          Body: req.file.buffer,
          ContentType: 'text/plain',
        })
      );

      res.send(
        '<p>Upload successful.</p><a href="/">Upload another</a>'
      );

    } catch (err2) {
      res.status(500).send(
        'Upload failed: ' + err2.message
      );
    }
  });
});

app.listen(
  PORT,
  () => console.log(
    `Uploader listening on ${PORT}`
  )
);
