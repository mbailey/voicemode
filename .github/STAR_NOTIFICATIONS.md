# GitHub Star Notifications Setup

This repository is configured to send push notifications to your phone when someone stars the repository.

## How It Works

1. **GitHub Action**: The workflow `.github/workflows/star-notification.yml` triggers on star events
2. **ntfy.sh**: Posts notification to your ntfy topic
3. **Your Phone**: Receive instant notification via ntfy app

## Setup Instructions

### 1. Install ntfy App

**iOS**: https://apps.apple.com/app/ntfy/id1625396347
**Android**: https://play.google.com/store/apps/details?id=io.heckel.ntfy

### 2. Choose Your ntfy Topic

Pick a unique topic name (e.g., `voicemode-stars-mike-bailey-xyz123`). This will be your notification channel.

**Important**: Use a unique, hard-to-guess topic name to prevent others from spamming your notifications.

### 3. Configure GitHub Secret

1. Go to your repository: https://github.com/mbailey/voicemode
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `NTFY_TOPIC`
5. Value: Your chosen topic name (e.g., `voicemode-stars-mike-bailey-xyz123`)
6. Click **Add secret**

### 4. Subscribe in ntfy App

1. Open the ntfy app on your phone
2. Tap the **+** button
3. Enter your topic name (same as the GitHub secret)
4. Tap **Subscribe**

### 5. Test the Notification

You can test the notification manually:

```bash
curl -H "Title: Test Notification" \
     -d "This is a test from your terminal" \
     https://ntfy.sh/your-topic-name
```

Replace `your-topic-name` with your actual topic.

## What You'll See

When someone stars the repository, you'll receive a notification like:

```
Title: VoiceMode ⭐ New Star!
Message: 🎉 username just starred voicemode! Total stars: 400
```

## Customization

Edit `.github/workflows/star-notification.yml` to customize:
- Notification title and message
- Priority level (min, low, default, high, max)
- Tags (for filtering in the app)
- Additional metadata

## Privacy & Security

- **ntfy.sh** is an open-source notification service
- Messages are not encrypted by default (consider self-hosting for sensitive data)
- Use a unique topic name to prevent unauthorized notifications
- No authentication required for basic usage

## Alternative: Self-Hosted ntfy

For enhanced privacy, you can self-host ntfy:

1. Deploy ntfy server: https://docs.ntfy.sh/install/
2. Update the workflow to use your ntfy server URL
3. Add authentication if desired

## Troubleshooting

**Not receiving notifications?**
1. Verify the GitHub secret `NTFY_TOPIC` is set correctly
2. Check you're subscribed to the correct topic in the ntfy app
3. Test with the curl command above
4. Check GitHub Actions logs for errors

**Notifications delayed?**
- GitHub Actions may take 30-60 seconds to trigger
- ntfy delivery is typically instant once the Action runs

## Related Projects

This setup was inspired by the bash-my-aws star notification system, which uses AWS Lambda and Slack. The ntfy approach is simpler and doesn't require AWS infrastructure.
