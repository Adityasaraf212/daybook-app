# Daybook — Android build

This folder is a ready-to-go Capacitor Android project. The actual compile step
needs a real internet connection to Google's Android SDK servers, which is why
it's built on GitHub's servers via GitHub Actions rather than locally.

## One-time setup (about 5 minutes)

1. Go to github.com and create a **new repository** (any name, e.g. `daybook-app`).
   Public or private both work — private is fine, GitHub Actions is free either way
   for a project this size.

2. On the new repo's page, click **"uploading an existing file"** and drag in
   everything from this folder (keep the folder structure — `.github/`, `android/`,
   `www/`, `package.json`, etc. all need to go in at the top level of the repo).
   If you'd rather use git from Terminal instead of the web upload:

   ```
   cd daybook-android
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
   git push -u origin main
   ```

3. That push automatically triggers the build. Click the **Actions** tab on your
   repo — you'll see "Build Android APK" running. It takes roughly 3-5 minutes.

4. Once it finishes (green checkmark), click into that run, scroll to
   **Artifacts**, and download `daybook-debug-apk`. Unzip it — that's your `.apk`.

## Installing it on your phone

Android blocks installs from unknown sources by default. On your Samsung S26:
Settings → Apps → Special access → Install unknown apps → (choose the app you
used to open the file, e.g. Chrome or Files) → allow. Then just tap the .apk file.

## Re-building after future changes

Any time you push a new commit to this repo, the Action re-runs automatically
and produces a fresh APK in Artifacts. To make a change, edit `www/index.html`
(that's the built app) or ask me to regenerate it and re-upload the updated file.

## Notifications

The three daily notifications (Settings → Notifications in the app) are scheduled
via @capacitor/local-notifications, which uses Android's real AlarmManager —
they'll fire even with the app fully closed, unlike the plain web version.
