const express = require('express');
const {
  S3Client,
  GetObjectCommand
} = require('@aws-sdk/client-s3');

const app = express();

const s3 = new S3Client({
  region: process.env.AWS_REGION
});

const BUCKET = process.env.BUCKET_NAME;
const PORT = process.env.PORT || 3000;

const streamToString = (stream) =>
  new Promise((resolve, reject) => {
    const chunks = [];

    stream.on(
      'data',
      (chunk) => chunks.push(chunk)
    );

    stream.on('error', reject);

    stream.on(
      'end',
      () => resolve(
        Buffer.concat(chunks)
          .toString('utf-8')
      )
    );
  });

app.get('/', async (req, res) => {
  try {
    const data = await s3.send(
      new GetObjectCommand({
        Bucket: BUCKET,
        Key: 'shared.txt',
      })
    );

    const content = await streamToString(
      data.Body
    );

    res.send(
      `<h1>Viewer</h1><pre>${content}</pre><a href="/">Refresh</a>`
    );

  } catch (err) {
    res.send(
      '<h1>Viewer</h1><p>No file uploaded yet.</p><a href="/">Refresh</a>'
    );
  }
});

app.listen(
  PORT,
  () => console.log(
    `Viewer listening on ${PORT}`
  )
);
