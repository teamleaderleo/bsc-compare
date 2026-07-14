package data.scripts;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.combat.BeamAPI;
import com.fs.starfarer.api.combat.BeamEffectPlugin;
import com.fs.starfarer.api.combat.CombatEngineAPI;

import java.awt.Color;
import org.lwjgl.util.vector.Vector2f;

import org.lazywizard.lazylib.combat.CombatUtils;

public class BSC_ImpulseBeamEffect implements BeamEffectPlugin {

    private float level = 0f;

    @Override
    public void advance(float amount, CombatEngineAPI engine, BeamAPI beam) {
        if (Global.getCombatEngine().isPaused()) {
            return;
        }

        Vector2f origin = new Vector2f(beam.getWeapon().getLocation());

        level = beam.getBrightness();
        Global.getCombatEngine().addHitParticle(origin, new Vector2f(), (float) Math.random() * 25f + 75f, 0.2f, 0.2f * level, new Color(148, 148, 224, 160));
        Global.getCombatEngine().addHitParticle(origin, new Vector2f(), (float) Math.random() * 25f + 125f, 0.2f, 0.2f * level, new Color(160, 160, 255, 255));
        if (beam.didDamageThisFrame() && beam.getDamageTarget() != null) {
            float force = level * amount * 5000f;
            CombatUtils.applyForce(beam.getDamageTarget(), beam.getWeapon().getCurrAngle(), force);
        }
    }
}
