diff --git a/requirements-dev.txt b/requirements-dev.txt
index 25a5554..49e1017 100644
--- a/requirements-dev.txt
+++ b/requirements-dev.txt
@@ -1,6 +1,9 @@
 # Optional development dependencies for RoboCAD.
 # Install with: python -m pip install -r requirements.txt -r requirements-dev.txt
 
 # Phase 14A+ simulation verification (optional). Core GEDA Bridge tests use
 # build123d + trimesh only; install mujoco to load generated MJCF files directly.
 mujoco>=3.0.0
+
+# Batch A multi-domain expansion: optional local offline embedding-based classifier.
+sentence-transformers>=3.0.0
ab5b9f3 chore(deps): add sentence-transformers as optional dev dependency
 requirements-dev.txt | 3 +++
 1 file changed, 3 insertions(+)
