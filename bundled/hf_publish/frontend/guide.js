// Markdown ships with this product version. Lines stay editable without a Markdown loader.
export const GUIDE = {
  chapters: [],
  sections: [
    {
      chapter: "using-the-app",
      anchor: "publish-a-dataset-to-hugging-face",
      markdown: [
        "## Publish a dataset to Hugging Face",
        "",
        "Keep the images and captions you want to share, then open **Import & export → More ways out → Publish to Hugging Face**.",
        "Configure the shared **Hugging Face token** in Plugins → Publish to Hugging Face → Settings with write permission on the destination repository. A read token can download models but cannot publish a dataset.",
        "Choose `username/repository`, visibility and license. The repository is private by default; the reference photo is excluded unless you explicitly include it.",
        "Review your rights to share the images and tick the consent checkbox before publishing. Exported images are fresh PNG copies without private metadata; captions and a dataset card accompany them.",
        "The dialog follows the upload and links to the resulting dataset. A missing or read-only token must be corrected in Settings. Cloud training is not required.",
      ].join("\n") + "\n",
    },
  ],
}
