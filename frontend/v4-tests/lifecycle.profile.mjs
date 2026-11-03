// A failed or incomplete launch provides no proof that the owned profile is closed.
export async function closeAndCleanOwnedProfile(context, profile, removeProfile) {
  if (!context) return false;
  await context.close();
  await removeProfile(profile, {recursive:true, force:true});
  return true;
}
