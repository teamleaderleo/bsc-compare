package data.scripts;

import com.fs.starfarer.api.combat.CombatEngineAPI;
import com.fs.starfarer.api.combat.EveryFrameWeaponEffectPlugin;
import com.fs.starfarer.api.combat.ShipAPI;
import com.fs.starfarer.api.combat.WeaponAPI;
import org.lazywizard.lazylib.MathUtils;

public class beans_deco_spinner implements EveryFrameWeaponEffectPlugin {


	private float angle = 0;
    private float turn_rate = 0;
    private boolean runOnce = true;
	public void advance(float amount, CombatEngineAPI engine, WeaponAPI weapon) {
		if (engine.isPaused()) return;
		if (!weapon.getShip().isAlive()) return;

        if(runOnce){
            turn_rate = weapon.getSpec().getBaseValue();
            runOnce =   false;
        }

        angle = MathUtils.clampAngle(angle+turn_rate*amount);

		weapon.setCurrAngle(weapon.getShip().getFacing()+weapon.getSlot().getAngle()+angle);
	}
}
