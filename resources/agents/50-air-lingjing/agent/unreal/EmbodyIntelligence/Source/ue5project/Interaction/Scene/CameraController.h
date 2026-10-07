#pragma once

#include "CoreMinimal.h"

class AEquipmentCameraActor;
class ASceneCameraActor;
class AActor;
class UWorld;

enum class ECameraType : uint8
{
	Equipment,
	Scene
};



class UE5PROJECT_API FCameraController
{
public:
	static FCameraController* Get();


	void Init(UWorld* InWorld);


	void SwitchTo(ECameraType InType);


	void FocusOn(AActor* InTarget);

	AActor* GetActiveCamera() const;

private:
	TWeakObjectPtr<AEquipmentCameraActor> EquipmentCamera;
	TWeakObjectPtr<ASceneCameraActor> SceneCamera;
	ECameraType ActiveType = ECameraType::Scene;
};
